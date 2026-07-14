"""Orquestra reparos seguros, específicos e verificáveis."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .core import CommandRunner, PrinterManagerError
from .cups_filters import CupsFilterService, FilterFinding, RepairAction
from .dependencies import DependencyService
from .health import HealthAction, HealthCheck, PrinterHealthService

HELPER = Path("/usr/libexec/neri-printer-helper")


class RepairStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class RepairResult:
    action: str
    status: RepairStatus
    message: str


class RepairService:
    """Executa somente ações previstas no catálogo interno e verifica o resultado."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=900)

    def _helper(self, action: str, *args: str) -> None:
        if not HELPER.exists():
            raise PrinterManagerError("Helper administrativo não instalado. Reinstale o aplicativo.")
        self.runner.run(["pkexec", str(HELPER), action, *args], check=True)

    def install_missing_dependencies(self, include_optional: bool = False) -> RepairResult:
        missing = DependencyService().missing(include_optional=include_optional)
        if not missing:
            return RepairResult("dependencies", RepairStatus.SKIPPED, "Dependências já instaladas")
        self._helper("install-packages", *missing)
        remaining = DependencyService().missing(include_optional=include_optional)
        if remaining:
            return RepairResult("dependencies", RepairStatus.FAILED, f"Pacotes ainda ausentes: {', '.join(remaining)}")
        return RepairResult("dependencies", RepairStatus.SUCCESS, "Dependências instaladas")

    def repair_health_check(self, check: HealthCheck) -> list[RepairResult]:
        """Executa a ação vinculada à linha e repete o diagnóstico correspondente."""
        if check.action is HealthAction.NONE:
            return [RepairResult(check.code, RepairStatus.SKIPPED, "Esta linha é informativa e não exige alteração.")]
        try:
            if check.action is HealthAction.INSTALL_DEPENDENCIES:
                results = [self.install_missing_dependencies(include_optional=False)]
            elif check.action is HealthAction.ENABLE_CUPS:
                self._helper("enable-service", "cups.service")
                results = [RepairResult("enable-cups", RepairStatus.SUCCESS, "CUPS ativado e iniciado.")]
            elif check.action is HealthAction.RESTART_CUPS:
                self._helper("restart-cups")
                results = [RepairResult("restart-cups", RepairStatus.SUCCESS, "CUPS reiniciado.")]
            elif check.action is HealthAction.ENABLE_AVAHI:
                self._helper("enable-service", "avahi-daemon.service")
                results = [RepairResult("enable-avahi", RepairStatus.SUCCESS, "Avahi ativado e iniciado.")]
            elif check.action is HealthAction.ENABLE_SAMBA:
                self._helper("enable-service", "smbd.service")
                results = [RepairResult("enable-samba", RepairStatus.SUCCESS, "Samba ativado e iniciado.")]
            elif check.action is HealthAction.CLEAR_JOBS:
                self._helper("clear-jobs")
                results = [RepairResult("clear-jobs", RepairStatus.SUCCESS, "Trabalhos pendentes cancelados.")]
            elif check.action is HealthAction.REPAIR_FILTER and isinstance(check.payload, FilterFinding):
                results = self.repair_filter_finding(check.payload)
            else:
                results = [RepairResult(check.code, RepairStatus.SKIPPED, "Não existe correção automática segura para esta condição.")]
        except PrinterManagerError as exc:
            return [RepairResult(check.code, RepairStatus.FAILED, str(exc))]

        current = {item.code: item for item in PrinterHealthService().run_all()}
        refreshed = current.get(check.code)
        if refreshed is None or refreshed.severity.value == "ok":
            results.append(RepairResult("verification", RepairStatus.SUCCESS, "A nova verificação confirmou que o problema foi resolvido."))
        else:
            results.append(RepairResult("verification", RepairStatus.FAILED, f"A condição ainda aparece: {refreshed.summary}"))
        return results

    def repair_safe_checks(self, checks: list[HealthCheck]) -> list[RepairResult]:
        results: list[RepairResult] = []
        seen: set[HealthAction] = set()
        for check in checks:
            if not check.safe_automatic or check.action is HealthAction.NONE:
                continue
            # Cada falha de filtro pode exigir um conjunto diferente de pacotes/ações.
            if check.action is HealthAction.REPAIR_FILTER:
                results.extend(self.repair_health_check(check))
                continue
            if check.action in seen:
                continue
            seen.add(check.action)
            results.extend(self.repair_health_check(check))
        return results or [RepairResult("automatic", RepairStatus.SKIPPED, "Nenhuma correção automática segura era necessária.")]

    def repair_filter_finding(self, finding: FilterFinding) -> list[RepairResult]:
        results: list[RepairResult] = []
        packages = CupsFilterService.packages_for(finding.actions)
        if packages:
            try:
                self._helper("reinstall-packages", *packages)
                results.append(RepairResult("reinstall-packages", RepairStatus.SUCCESS, ", ".join(packages)))
            except PrinterManagerError as exc:
                return [RepairResult("reinstall-packages", RepairStatus.FAILED, str(exc))]

        if RepairAction.FIX_PERMISSIONS in finding.actions:
            try:
                self._helper("fix-cups-permissions")
                results.append(RepairResult("fix-permissions", RepairStatus.SUCCESS, "Permissões oficiais do CUPS verificadas"))
            except PrinterManagerError as exc:
                results.append(RepairResult("fix-permissions", RepairStatus.FAILED, str(exc)))

        if RepairAction.CHECK_PPD in finding.actions:
            results.append(RepairResult("check-ppd", RepairStatus.SKIPPED, "O driver pertence à fila afetada. Remova e reinstale a fila escolhendo o modelo exato."))
        if RepairAction.CHECK_BACKEND in finding.actions:
            results.append(RepairResult("check-backend", RepairStatus.SKIPPED, "Confira IP/hostname, URI, compartilhamento e credenciais da impressora."))
        if RepairAction.RESTART_CUPS in finding.actions:
            try:
                self._helper("restart-cups")
                results.append(RepairResult("restart-cups", RepairStatus.SUCCESS, "CUPS reiniciado"))
            except PrinterManagerError as exc:
                results.append(RepairResult("restart-cups", RepairStatus.FAILED, str(exc)))

        post = CupsFilterService().diagnose()
        if any(item.code == finding.code for item in post):
            results.append(RepairResult("verification", RepairStatus.FAILED, "A condição ainda aparece na verificação atual"))
        else:
            results.append(RepairResult("verification", RepairStatus.SUCCESS, "Correção verificada; a condição não reapareceu"))
        return results
