"""Serviços centrais do Neri Printer Manager.

A camada não depende da interface gráfica. Isso facilita testes, uso pela CLI e
futuras interfaces. Comandos são executados sem shell para reduzir o risco de
injeção e sempre passam por validação centralizada.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from enum import Enum
import json
import logging
from pathlib import Path
import re
import shutil
import socket
import subprocess
from urllib.parse import urlparse

LOG = logging.getLogger(__name__)
_QUEUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,126}$")
_JOB_RE = re.compile(r"^[A-Za-z0-9_.-]+-[0-9]+$")
_ALLOWED_SCHEMES = {"ipp", "ipps", "http", "https", "socket", "lpd", "smb", "usb"}


class PrinterManagerError(RuntimeError):
    """Erro esperado que pode ser exibido diretamente ao usuário."""


class Severity(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Printer:
    name: str
    state: str
    enabled: bool
    accepting: bool
    device_uri: str | None = None


@dataclass(frozen=True, slots=True)
class PrintJob:
    job_id: str
    owner: str
    size: str
    submitted: str


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    uri: str
    protocol: str
    description: str


@dataclass(frozen=True, slots=True)
class DiagnosticItem:
    key: str
    title: str
    severity: Severity
    message: str
    remediation: str | None = None


@dataclass(frozen=True, slots=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def validate_queue_name(value: str) -> str:
    value = value.strip()
    if not _QUEUE_RE.fullmatch(value):
        raise PrinterManagerError(
            "Nome de fila inválido. Use letras, números, ponto, hífen ou sublinhado."
        )
    return value


def validate_job_id(value: str) -> str:
    value = value.strip()
    if not _JOB_RE.fullmatch(value):
        raise PrinterManagerError("Identificador de trabalho inválido.")
    return value


def validate_device_uri(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise PrinterManagerError("Protocolo não permitido para a impressora.")
    if parsed.scheme != "usb" and not parsed.netloc:
        raise PrinterManagerError("URI da impressora incompleta.")
    if any(char in value for char in ("\n", "\r", "\x00")):
        raise PrinterManagerError("URI contém caracteres inválidos.")
    return value


class CommandRunner:
    """Executa ferramentas do sistema com timeout e saída capturada."""

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    @staticmethod
    def exists(command: str) -> bool:
        return shutil.which(command) is not None

    def run(
        self,
        args: Sequence[str],
        *,
        privileged: bool = False,
        check: bool = True,
    ) -> CommandResult:
        if not args:
            raise ValueError("Comando vazio")
        command = [str(part) for part in args]
        if privileged:
            if not self.exists("pkexec"):
                raise PrinterManagerError("pkexec não está instalado.")
            command.insert(0, "pkexec")
        LOG.info("Executando comando: %s", command[0])
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PrinterManagerError(f"Falha ao executar {command[0]}: {exc}") from exc
        result = CommandResult(
            tuple(command),
            completed.returncode,
            completed.stdout.strip(),
            completed.stderr.strip(),
        )
        if check and result.returncode != 0:
            detail = result.stderr or result.stdout or "sem detalhes"
            raise PrinterManagerError(f"Comando falhou ({result.returncode}): {detail}")
        return result


class CupsService:
    """Integração com CUPS através das ferramentas oficiais do sistema."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def list_printers(self) -> list[Printer]:
        printers: list[Printer] = []
        result = self.runner.run(["lpstat", "-p"], check=False)
        accepting = self._accepting_map()
        devices = self._device_map()
        for line in result.stdout.splitlines():
            match = re.match(r"printer\s+(\S+)\s+(.*)", line)
            if not match:
                continue
            name, state = match.groups()
            printers.append(
                Printer(
                    name=name,
                    state=state,
                    enabled="disabled" not in state.lower(),
                    accepting=accepting.get(name, True),
                    device_uri=devices.get(name),
                )
            )
        return printers

    def _accepting_map(self) -> dict[str, bool]:
        result = self.runner.run(["lpstat", "-a"], check=False)
        return {
            line.split(maxsplit=1)[0]: "not accepting" not in line.lower()
            for line in result.stdout.splitlines()
            if line.strip()
        }

    def _device_map(self) -> dict[str, str]:
        result = self.runner.run(["lpstat", "-v"], check=False)
        devices: dict[str, str] = {}
        for line in result.stdout.splitlines():
            match = re.match(r"device for (\S+):\s+(.+)", line)
            if match:
                devices[match.group(1)] = match.group(2)
        return devices

    def add_printer(self, name: str, uri: str, model: str = "everywhere") -> None:
        safe_name = validate_queue_name(name)
        safe_uri = validate_device_uri(uri)
        self.runner.run(
            ["/usr/sbin/lpadmin", "-p", safe_name, "-E", "-v", safe_uri, "-m", model],
            privileged=True,
        )

    def remove_printer(self, name: str) -> None:
        self.runner.run(
            ["/usr/sbin/lpadmin", "-x", validate_queue_name(name)], privileged=True
        )

    def pause(self, name: str) -> None:
        self.runner.run(
            ["/usr/sbin/cupsdisable", validate_queue_name(name)], privileged=True
        )

    def resume(self, name: str) -> None:
        safe_name = validate_queue_name(name)
        self.runner.run(["/usr/sbin/cupsenable", safe_name], privileged=True)
        self.runner.run(["/usr/sbin/cupsaccept", safe_name], privileged=True)

    def print_test_page(self, name: str) -> None:
        self.runner.run(
            ["lp", "-d", validate_queue_name(name), "/usr/share/cups/data/testprint"]
        )


class JobService:
    """Consulta e cancela trabalhos de impressão."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def list_jobs(self) -> list[PrintJob]:
        jobs: list[PrintJob] = []
        result = self.runner.run(["lpstat", "-o"], check=False)
        for line in result.stdout.splitlines():
            parts = line.split(maxsplit=4)
            if len(parts) >= 3:
                jobs.append(
                    PrintJob(
                        job_id=parts[0],
                        owner=parts[1],
                        size=parts[2],
                        submitted=" ".join(parts[3:]) if len(parts) > 3 else "",
                    )
                )
        return jobs

    def cancel(self, job_id: str) -> None:
        self.runner.run(["cancel", validate_job_id(job_id)])


class DiscoveryService:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=20)

    def discover(self) -> list[DiscoveredDevice]:
        devices: dict[str, DiscoveredDevice] = {}
        if self.runner.exists("lpinfo"):
            result = self.runner.run(["lpinfo", "-v"], check=False)
            for line in result.stdout.splitlines():
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    protocol, uri = parts
                    devices[uri] = DiscoveredDevice(uri, protocol, "Detectada pelo CUPS")
        return sorted(devices.values(), key=lambda item: (item.protocol, item.uri))


class DiagnosticService:
    REQUIRED = ("lpstat", "lpinfo", "lpadmin", "systemctl", "pkexec")

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=10)

    def run_all(self) -> list[DiagnosticItem]:
        items = [self._command(name) for name in self.REQUIRED]
        items.append(self._cups_service())
        items.append(self._cups_port())
        return items

    def _command(self, name: str) -> DiagnosticItem:
        if self.runner.exists(name):
            return DiagnosticItem(f"command.{name}", name, Severity.OK, "Disponível")
        return DiagnosticItem(
            f"command.{name}",
            name,
            Severity.ERROR,
            "Não encontrado",
            f"Instale o pacote que fornece {name}.",
        )

    def _cups_service(self) -> DiagnosticItem:
        result = self.runner.run(["systemctl", "is-active", "cups.service"], check=False)
        if result.stdout == "active":
            return DiagnosticItem("cups.service", "Serviço CUPS", Severity.OK, "Ativo")
        return DiagnosticItem(
            "cups.service",
            "Serviço CUPS",
            Severity.ERROR,
            result.stdout or result.stderr or "Inativo",
            "Execute: sudo systemctl enable --now cups",
        )

    def _cups_port(self) -> DiagnosticItem:
        try:
            with socket.create_connection(("127.0.0.1", 631), timeout=2):
                return DiagnosticItem("cups.port", "Porta 631", Severity.OK, "Respondendo")
        except OSError as exc:
            return DiagnosticItem(
                "cups.port",
                "Porta 631",
                Severity.ERROR,
                str(exc),
                "Verifique o serviço CUPS e o arquivo cupsd.conf.",
            )


def write_report(path: Path, printers: list[Printer], diagnostics: list[DiagnosticItem]) -> Path:
    """Grava um relatório técnico portátil em JSON."""
    payload = {
        "printers": [asdict(item) for item in printers],
        "diagnostics": [asdict(item) for item in diagnostics],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
