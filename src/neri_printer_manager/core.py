"""Serviços centrais do Neri Printer Manager."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import socket
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from .security import contains_control_characters, redact_data, redact_text

LOG = logging.getLogger(__name__)
_QUEUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,126}$")
_JOB_RE = re.compile(r"^[A-Za-z0-9_.-]+-[0-9]+$")
_ALLOWED_SCHEMES = {"ipp", "ipps", "http", "https", "socket", "lpd", "smb", "usb", "hp"}
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:+-]{0,511}$")
ADMIN_HELPER = Path("/usr/libexec/neri-printer-helper")
SAFE_COMMAND_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
CUPS_SOCKET_PATHS = (Path("/run/cups/cups.sock"), Path("/var/run/cups/cups.sock"))


def local_cups_server() -> str:
    """Retorna somente o servidor CUPS deste computador."""

    return str(next((path for path in CUPS_SOCKET_PATHS if path.exists()), "localhost"))


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
    automatic: bool = False


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
    if len(value) > 255 or not _JOB_RE.fullmatch(value):
        raise PrinterManagerError("Identificador de trabalho inválido.")
    return value


def validate_device_uri(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 2048:
        raise PrinterManagerError("URI da impressora vazia ou muito longa.")
    if (
        contains_control_characters(value)
        or any(character.isspace() for character in value)
        or re.search(r"%(?:0[0-9a-f]|1[0-9a-f]|7f)", value, re.IGNORECASE)
    ):
        raise PrinterManagerError("URI contém caracteres inválidos.")
    try:
        parsed = urlparse(value)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
    except ValueError as exc:
        raise PrinterManagerError("URI da impressora inválida.") from exc
    if scheme not in _ALLOWED_SCHEMES:
        raise PrinterManagerError("Protocolo não permitido para a impressora.")
    if scheme in {"usb", "hp"}:
        if not parsed.netloc and not parsed.path.strip("/"):
            raise PrinterManagerError("URI USB incompleta.")
        if scheme == "hp" and not parsed.path.lower().startswith("/usb/"):
            raise PrinterManagerError("A URI HPLIP não representa uma impressora USB.")
        return value
    if not parsed.netloc or not hostname:
        raise PrinterManagerError("URI da impressora incompleta.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise PrinterManagerError("Porta inválida na URI da impressora.") from exc
    if port is not None and not 1 <= port <= 65535:
        raise PrinterManagerError("Porta inválida na URI da impressora.")
    if scheme == "socket" and port is None:
        raise PrinterManagerError("A conexão JetDirect precisa informar uma porta.")
    if scheme == "smb" and not parsed.path.strip("/"):
        raise PrinterManagerError("Informe o nome do compartilhamento SMB.")
    if parsed.username is not None and scheme != "smb":
        raise PrinterManagerError("Credenciais na URI são permitidas somente para SMB.")
    return value


def validate_driver_model(value: str) -> str:
    """Valida o identificador retornado por ``lpinfo -m``."""

    model = value.strip()
    if not _MODEL_RE.fullmatch(model) or ".." in model:
        raise PrinterManagerError("Identificador de driver inválido.")
    return model


class CommandRunner:
    """Executa ferramentas do sistema com timeout e saída previsível."""

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    @staticmethod
    def exists(command: str) -> bool:
        return shutil.which(command, path=SAFE_COMMAND_PATH) is not None

    def run(
        self,
        args: Sequence[str],
        *,
        privileged: bool = False,
        check: bool = True,
        input_text: str | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        if not args:
            raise ValueError("Comando vazio")
        command = [str(part) for part in args]
        if privileged:
            if not self.exists("pkexec"):
                raise PrinterManagerError("pkexec não está instalado.")
            command.insert(0, "pkexec")
        LOG.info("Executando comando: %s", command[0])
        env = os.environ.copy()
        for key in tuple(env):
            if key.startswith("CUPS_"):
                env.pop(key)
        env.update(
            {
                "CUPS_SERVER": local_cups_server(),
                "LC_ALL": "C",
                "LANG": "C",
                "LANGUAGE": "C",
                "PATH": SAFE_COMMAND_PATH,
            }
        )
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                input=input_text,
                timeout=self.timeout if timeout is None else timeout,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise PrinterManagerError(f"O comando {command[0]} excedeu o tempo limite.") from exc
        except OSError as exc:
            raise PrinterManagerError(f"Falha ao executar {command[0]}: {exc}") from exc
        result = CommandResult(
            tuple(redact_text(part) for part in command),
            completed.returncode,
            redact_text(completed.stdout.strip()),
            redact_text(completed.stderr.strip()),
        )
        if check and result.returncode != 0:
            detail = result.stderr or result.stdout or "sem detalhes"
            raise PrinterManagerError(f"Comando falhou ({result.returncode}): {detail}")
        return result


def run_admin_action(
    runner: CommandRunner,
    action: str,
    *args: str,
    input_text: str | None = None,
) -> CommandResult:
    """Executa uma ação limitada pelo helper autorizado no PolicyKit."""

    if not ADMIN_HELPER.is_file():
        raise PrinterManagerError(
            "Componente administrativo não instalado. Execute novamente o instalador."
        )
    long_actions = {"install-packages", "reinstall-packages"}
    action_timeout = 2100 if action in long_actions else 300
    return runner.run(
        ["pkexec", str(ADMIN_HELPER), action, *args],
        check=True,
        input_text=input_text,
        timeout=action_timeout,
    )


class CupsService:
    """Integração com CUPS através das ferramentas oficiais do sistema."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def list_printers(self, *, include_automatic: bool = False) -> list[Printer]:
        printers: list[Printer] = []
        result = self.runner.run(["lpstat", "-p"], check=False)
        accepting = self._accepting_map()
        devices = self._device_map()
        for line in result.stdout.splitlines():
            match = re.match(r"printer\s+(\S+)\s+(.*)", line)
            if not match:
                continue
            name, state = match.groups()
            device_uri = devices.get(name)
            automatic = self._is_automatic_uri(device_uri)
            if automatic and not include_automatic:
                continue
            printers.append(
                Printer(
                    name=name,
                    state=state,
                    enabled="disabled" not in state.lower(),
                    accepting=accepting.get(name, True),
                    device_uri=device_uri,
                    automatic=automatic,
                )
            )
        return printers

    @staticmethod
    def _is_automatic_uri(uri: str | None) -> bool:
        """Reconhece filas efêmeras criadas pelo ``cups-browsed``."""

        return bool(uri and uri.lower().startswith("implicitclass:"))

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
        safe_uri = validate_device_uri(uri)
        if urlparse(safe_uri).username is not None:
            raise PrinterManagerError(
                "Use o fluxo autenticado de SMB para que a senha não seja enviada "
                "como argumento de processo."
            )
        run_admin_action(
            self.runner,
            "add",
            validate_queue_name(name),
            safe_uri,
            validate_driver_model(model),
        )

    def add_authenticated_printer(
        self,
        name: str,
        uri: str,
        model: str,
        username: str,
        password: str,
    ) -> None:
        """Cria uma fila SMB sem colocar a senha nos argumentos do ``pkexec``."""

        safe_uri = validate_device_uri(uri)
        parsed = urlparse(safe_uri)
        if parsed.scheme.lower() != "smb" or parsed.username is not None:
            raise PrinterManagerError("A conexão autenticada precisa de uma URI SMB sem senha.")
        safe_user = username.strip()
        if (
            not safe_user
            or len(safe_user) > 256
            or contains_control_characters(safe_user)
            or len(password) > 256
            or contains_control_characters(password)
        ):
            raise PrinterManagerError("Usuário ou senha SMB inválidos.")
        run_admin_action(
            self.runner,
            "add-smb",
            validate_queue_name(name),
            safe_uri,
            validate_driver_model(model),
            safe_user,
            input_text=f"{password}\n",
        )

    def remove_printer(self, name: str) -> None:
        run_admin_action(self.runner, "remove", validate_queue_name(name))

    def pause(self, name: str) -> None:
        run_admin_action(self.runner, "pause", validate_queue_name(name))

    def resume(self, name: str) -> None:
        run_admin_action(self.runner, "resume", validate_queue_name(name))

    def queue_exists(self, name: str) -> bool:
        safe_name = validate_queue_name(name)
        expected = safe_name.casefold()
        return any(
            printer.name.casefold() == expected
            for printer in self.list_printers(include_automatic=True)
        )

    def verify_printer(self, name: str) -> None:
        safe_name = validate_queue_name(name)
        result = self.runner.run(["lpstat", "-p", safe_name], check=False)
        if result.returncode != 0:
            raise PrinterManagerError(
                result.stderr or result.stdout or "A fila não apareceu no CUPS após a instalação."
            )

    def set_default(self, name: str) -> None:
        safe_name = validate_queue_name(name)
        self.runner.run(["lpoptions", "-d", safe_name])

    def default_printer(self) -> str | None:
        result = self.runner.run(["lpstat", "-d"], check=False)
        if result.returncode != 0 or ":" not in result.stdout:
            return None
        return result.stdout.split(":", 1)[1].strip() or None

    def print_test_page(self, name: str) -> None:
        self.runner.run(["lp", "-d", validate_queue_name(name), "/usr/share/cups/data/testprint"])


class JobService:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def list_jobs(self) -> list[PrintJob]:
        jobs: list[PrintJob] = []
        result = self.runner.run(["lpstat", "-o"], check=False)
        for line in result.stdout.splitlines():
            parts = line.split(maxsplit=4)
            if len(parts) >= 3:
                jobs.append(PrintJob(parts[0], parts[1], parts[2], " ".join(parts[3:])))
        return jobs

    def cancel(self, job_id: str) -> None:
        run_admin_action(self.runner, "cancel-job", validate_job_id(job_id))


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
                    try:
                        safe_uri = validate_device_uri(uri)
                    except PrinterManagerError:
                        continue
                    devices[safe_uri] = DiscoveredDevice(
                        safe_uri,
                        protocol,
                        "Detectada pelo CUPS",
                    )
        return sorted(devices.values(), key=lambda item: (item.protocol, item.uri))


class DiagnosticService:
    REQUIRED = ("lpstat", "lpinfo", "lpadmin", "lpoptions", "systemctl", "pkexec")

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=10)

    def run_all(self) -> list[DiagnosticItem]:
        items = [self._command(name) for name in self.REQUIRED]
        items.append(self._admin_helper())
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

    @staticmethod
    def _admin_helper() -> DiagnosticItem:
        if ADMIN_HELPER.is_file() and os.access(ADMIN_HELPER, os.X_OK):
            return DiagnosticItem("admin.helper", "Helper administrativo", Severity.OK, "Instalado")
        return DiagnosticItem(
            "admin.helper",
            "Helper administrativo",
            Severity.ERROR,
            "Não encontrado",
            "Reinstale o Neri Printer Manager.",
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
                "Verifique o serviço CUPS e cupsd.conf.",
            )


def write_report(path: Path, printers: list[Printer], diagnostics: list[DiagnosticItem]) -> Path:
    payload = {
        "printers": [asdict(item) for item in printers],
        "diagnostics": [asdict(item) for item in diagnostics],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(redact_data(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path
