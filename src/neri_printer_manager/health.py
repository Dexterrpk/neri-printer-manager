"""Diagnóstico unificado, explicável e acionável do ambiente de impressão."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import getpass
import socket
from typing import Any

from .core import CommandRunner, Severity
from .cups_filters import CupsFilterService, FilterFinding
from .dependencies import DependencyService, PackageState


class HealthAction(str, Enum):
    NONE = "none"
    INSTALL_DEPENDENCIES = "install_dependencies"
    ENABLE_CUPS = "enable_cups"
    RESTART_CUPS = "restart_cups"
    ENABLE_AVAHI = "enable_avahi"
    ENABLE_SAMBA = "enable_samba"
    REPAIR_FILTER = "repair_filter"
    CLEAR_JOBS = "clear_jobs"


@dataclass(frozen=True, slots=True)
class HealthCheck:
    code: str
    category: str
    title: str
    severity: Severity
    summary: str
    details: str
    action: HealthAction = HealthAction.NONE
    action_label: str = "Nenhuma ação necessária"
    safe_automatic: bool = False
    payload: Any = field(default=None, repr=False, compare=False)


class PrinterHealthService:
    """Executa verificações independentes; uma falha não cancela as demais."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=15)

    def run_all(self) -> list[HealthCheck]:
        checks: list[HealthCheck] = []
        probes = (
            self._dependencies,
            self._cups_service,
            self._cups_scheduler,
            self._cups_port,
            self._avahi_service,
            self._samba_service,
            self._queues,
            self._jobs,
            self._authorization,
            self._filters,
        )
        for probe in probes:
            try:
                checks.extend(probe())
            except Exception as exc:  # diagnóstico nunca deve derrubar a interface
                checks.append(
                    HealthCheck(
                        f"probe.{probe.__name__}",
                        "Diagnóstico",
                        "Verificação não concluída",
                        Severity.WARNING,
                        "Uma verificação isolada falhou, mas as demais continuaram.",
                        str(exc),
                    )
                )
        order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.OK: 2}
        return sorted(checks, key=lambda item: (order[item.severity], item.category, item.title))

    def _dependencies(self) -> list[HealthCheck]:
        statuses = DependencyService(self.runner).audit()
        required = [s.requirement.name for s in statuses if s.requirement.required and s.state is PackageState.MISSING]
        optional = [s.requirement.name for s in statuses if not s.requirement.required and s.state is PackageState.MISSING]
        if required:
            return [HealthCheck(
                "dependencies.required", "Componentes", "Dependências obrigatórias ausentes",
                Severity.ERROR, "O programa pode abrir, mas algumas funções não funcionarão.",
                ", ".join(required), HealthAction.INSTALL_DEPENDENCIES,
                "Instalar componentes ausentes", True,
            )]
        detail = "Todos os componentes obrigatórios estão instalados."
        if optional:
            detail += f" Opcionais ausentes: {', '.join(optional)}."
        return [HealthCheck(
            "dependencies.ok", "Componentes", "Dependências do sistema", Severity.OK,
            "Componentes essenciais disponíveis.", detail,
        )]

    def _service(self, unit: str, title: str, action: HealthAction, label: str, optional: bool = False) -> list[HealthCheck]:
        result = self.runner.run(["systemctl", "is-active", unit], check=False)
        if result.stdout == "active":
            return [HealthCheck(f"service.{unit}", "Serviços", title, Severity.OK, "Ativo e respondendo.", unit)]
        severity = Severity.WARNING if optional else Severity.ERROR
        return [HealthCheck(
            f"service.{unit}", "Serviços", title, severity,
            "O serviço está parado ou indisponível.", result.stdout or result.stderr or "inativo",
            action, label, True,
        )]

    def _cups_service(self) -> list[HealthCheck]:
        return self._service("cups.service", "Servidor CUPS", HealthAction.ENABLE_CUPS, "Ativar e iniciar CUPS")

    def _avahi_service(self) -> list[HealthCheck]:
        return self._service("avahi-daemon.service", "Descoberta Avahi/mDNS", HealthAction.ENABLE_AVAHI, "Ativar descoberta de rede", optional=True)

    def _samba_service(self) -> list[HealthCheck]:
        return self._service("smbd.service", "Compartilhamento Samba", HealthAction.ENABLE_SAMBA, "Ativar compartilhamento Windows", optional=True)

    def _cups_scheduler(self) -> list[HealthCheck]:
        result = self.runner.run(["lpstat", "-r"], check=False)
        if result.returncode == 0 and "running" in result.stdout.lower():
            return [HealthCheck("cups.scheduler", "CUPS", "Agendador de impressão", Severity.OK, "Aceitando operações.", result.stdout)]
        return [HealthCheck(
            "cups.scheduler", "CUPS", "Agendador de impressão", Severity.ERROR,
            "O CUPS não está aceitando operações normalmente.", result.stderr or result.stdout or "sem resposta",
            HealthAction.RESTART_CUPS, "Reiniciar CUPS", True,
        )]

    def _cups_port(self) -> list[HealthCheck]:
        try:
            with socket.create_connection(("127.0.0.1", 631), timeout=2):
                return [HealthCheck("cups.port", "CUPS", "Porta local 631", Severity.OK, "Interface local do CUPS respondendo.", "127.0.0.1:631")]
        except OSError as exc:
            return [HealthCheck(
                "cups.port", "CUPS", "Porta local 631", Severity.ERROR,
                "A interface local do CUPS não respondeu.", str(exc),
                HealthAction.RESTART_CUPS, "Reiniciar CUPS", True,
            )]

    def _queues(self) -> list[HealthCheck]:
        result = self.runner.run(["lpstat", "-p"], check=False)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            return [HealthCheck("queues.none", "Filas", "Impressoras instaladas", Severity.WARNING, "Nenhuma fila local encontrada.", "Instale uma impressora para começar.")]
        disabled = [line.split()[1] for line in lines if "disabled" in line.lower() and len(line.split()) > 1]
        if disabled:
            return [HealthCheck(
                "queues.disabled", "Filas", "Filas pausadas ou desativadas", Severity.WARNING,
                f"{len(disabled)} fila(s) não estão prontas para imprimir.", ", ".join(disabled),
                HealthAction.RESTART_CUPS, "Reiniciar CUPS e revisar filas", False,
            )]
        return [HealthCheck("queues.ok", "Filas", "Impressoras instaladas", Severity.OK, f"{len(lines)} fila(s) disponíveis.", "Nenhuma fila desativada detectada.")]

    def _jobs(self) -> list[HealthCheck]:
        result = self.runner.run(["lpstat", "-o"], check=False)
        jobs = [line for line in result.stdout.splitlines() if line.strip()]
        if not jobs:
            return [HealthCheck("jobs.ok", "Fila", "Trabalhos pendentes", Severity.OK, "Nenhum trabalho preso na fila.", "Fila limpa.")]
        return [HealthCheck(
            "jobs.pending", "Fila", "Trabalhos aguardando", Severity.WARNING,
            f"Existem {len(jobs)} trabalho(s) pendente(s).", "\n".join(jobs[:10]),
            HealthAction.CLEAR_JOBS, "Cancelar trabalhos pendentes", False,
        )]

    def _authorization(self) -> list[HealthCheck]:
        user = getpass.getuser()
        if self.runner.exists("pkexec"):
            return [HealthCheck("auth.pkexec", "Permissões", "Autenticação administrativa", Severity.OK, "PolicyKit disponível.", f"Usuário atual: {user}")]
        return [HealthCheck(
            "auth.pkexec", "Permissões", "Autenticação administrativa", Severity.ERROR,
            "Ações de correção não poderão pedir autorização.", "pkexec não encontrado",
            HealthAction.INSTALL_DEPENDENCIES, "Instalar PolicyKit", True,
        )]

    def _filters(self) -> list[HealthCheck]:
        findings = CupsFilterService(self.runner).diagnose()
        if not findings:
            return [HealthCheck("filters.ok", "Conversão", "Filtros e drivers", Severity.OK, "Nenhuma falha atual encontrada.", "Filtros, backends e pacotes essenciais verificados.")]
        return [self._from_filter(item) for item in findings]

    @staticmethod
    def _from_filter(finding: FilterFinding) -> HealthCheck:
        labels = {
            "reinstall_filters": "Reinstalar filtros do CUPS",
            "reinstall_ghostscript": "Reinstalar Ghostscript",
            "check_ppd": "Revisar driver/PPD da fila",
            "fix_permissions": "Corrigir permissões do CUPS",
            "restart_cups": "Reiniciar CUPS",
            "check_backend": "Revisar conexão e credenciais",
            "clear_stale_jobs": "Limpar trabalhos travados",
        }
        action_text = "; ".join(labels.get(action.value, action.value) for action in finding.actions)
        automatic = bool(finding.actions) and all(action.value not in {"check_ppd", "check_backend"} for action in finding.actions)
        return HealthCheck(
            f"filter.{finding.code}", "Conversão", finding.title, finding.severity,
            "Foi encontrada uma falha atual relacionada ao processamento da impressão.",
            f"{finding.source}: {finding.evidence}", HealthAction.REPAIR_FILTER,
            action_text or "Mostrar orientação", automatic, finding,
        )
