"""Operações administrativas estritamente limitadas para uso via PolicyKit.

Este módulo é executado pelo wrapper ``/usr/libexec/neri-printer-helper``.
Nenhuma ação aceita comandos arbitrários e todos os valores vindos da interface
são validados novamente depois da elevação de privilégio.
"""

from __future__ import annotations

import fcntl
import hashlib
import importlib
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote, urlparse, urlunparse

from .core import (
    PrinterManagerError,
    local_cups_server,
    validate_device_uri,
    validate_driver_model,
    validate_job_id,
    validate_queue_name,
)
from .dependencies import CORE_PACKAGES
from .security import contains_control_characters, redact_text

ALLOWED_PACKAGES = {requirement.name for requirement in CORE_PACKAGES}
ALLOWED_SERVICES = {
    "cups.service",
    "avahi-daemon.service",
    "smbd.service",
}
CUPS_EXEC_DIRS = (
    Path("/usr/lib/cups/filter"),
    Path("/usr/lib/cups/backend"),
)
BACKUP_SOURCES = (
    Path("/etc/cups/cupsd.conf"),
    Path("/etc/cups/printers.conf"),
    Path("/etc/cups/ppd"),
    Path("/etc/samba/smb.conf"),
)
SAMBA_CONFIG = Path("/etc/samba/smb.conf")
SAMBA_SPOOL = Path("/var/spool/samba")
QUEUE_LOCK = Path("/run/lock/neri-printer-manager.queue.lock")
COMMAND_ENV = {
    "CUPS_SERVER": local_cups_server(),
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LC_ALL": "C",
    "LANG": "C",
    "LANGUAGE": "C",
}


def _fail(message: object, code: int = 2) -> int:
    print(redact_text(message), file=sys.stderr)
    return code


def _execute(
    command: list[str],
    *,
    input_text: str | None = None,
    timeout: float = 90,
) -> int:
    """Executa um comando absoluto e devolve somente saída higienizada."""

    try:
        completed = subprocess.run(
            command,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=COMMAND_ENV,
        )
    except subprocess.TimeoutExpired:
        return _fail(f"A operação {command[0]} excedeu o tempo limite.", 124)
    except OSError as exc:
        return _fail(exc, 1)
    if completed.stdout:
        print(redact_text(completed.stdout), end="")
    if completed.stderr:
        print(redact_text(completed.stderr), end="", file=sys.stderr)
    return completed.returncode


def _packages(values: list[str]) -> list[str]:
    normalized = sorted(set(values))
    if not normalized or any(value not in ALLOWED_PACKAGES for value in normalized):
        raise PrinterManagerError("Pacote não autorizado.")
    return normalized


def _install_packages(values: list[str], *, reinstall: bool = False) -> int:
    packages = _packages(values)
    update_result = _execute(["/usr/bin/apt-get", "update"], timeout=600)
    if update_result:
        return update_result
    command = ["/usr/bin/apt-get", "install", "-y"]
    if reinstall:
        command.append("--reinstall")
    return _execute([*command, *packages], timeout=1200)


def _enable_service(name: str) -> int:
    if name not in ALLOWED_SERVICES:
        raise PrinterManagerError("Serviço não autorizado.")
    return _execute(["/usr/bin/systemctl", "enable", "--now", name])


def _looks_executable(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            header = handle.read(4)
    except OSError:
        return False
    return header.startswith(b"#!") or header == b"\x7fELF"


def _fix_cups_permissions() -> int:
    for directory in CUPS_EXEC_DIRS:
        if not directory.is_dir():
            continue
        for entry in directory.iterdir():
            if (
                entry.is_file()
                and not entry.is_symlink()
                and _looks_executable(entry)
                and not os.access(entry, os.X_OK)
            ):
                entry.chmod((entry.stat().st_mode & 0o7777) | 0o111)
    return 0


def _queue_exists(name: str) -> bool:
    """Consulta todas as filas e compara sem diferenciar maiúsculas/minúsculas."""

    try:
        completed = subprocess.run(
            ["/usr/bin/lpstat", "-p"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            env=COMMAND_ENV,
        )
    except subprocess.TimeoutExpired as exc:
        raise PrinterManagerError("O CUPS não respondeu ao consultar as filas.") from exc
    except OSError as exc:
        raise PrinterManagerError(f"Não foi possível consultar o CUPS: {redact_text(exc)}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        if "no destinations added" in detail.lower():
            return False
        raise PrinterManagerError(
            f"Não foi possível confirmar as filas existentes: {redact_text(detail or 'sem resposta')}"
        )
    expected = name.casefold()
    return any(
        match.group(1).casefold() == expected
        for line in completed.stdout.splitlines()
        if (match := re.match(r"printer\s+(\S+)\s+", line))
    )


def _ensure_new_queue(name: str) -> str:
    queue = validate_queue_name(name)
    if _queue_exists(queue):
        raise PrinterManagerError(
            f"A fila {queue} já existe. Escolha outro nome para não substituí-la."
        )
    return queue


@contextmanager
def _queue_creation_lock() -> Iterator[None]:
    descriptor = os.open(
        QUEUE_LOCK,
        os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise PrinterManagerError("O arquivo de bloqueio administrativo é inválido.")
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, 0, 0)
        deadline = time.monotonic() + 180
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PrinterManagerError(
                        "Outra instalação de impressora ainda está em andamento."
                    )
                time.sleep(0.1)
        yield
    finally:
        os.close(descriptor)


def _cleanup_failed_queue(queue: str) -> None:
    """Remove somente a fila cuja ausência foi confirmada sob o bloqueio."""

    if _queue_exists(queue):
        _execute(["/usr/sbin/lpadmin", "-x", queue])


def _stdin_secret(*, allow_empty: bool = False) -> str:
    secret = sys.stdin.readline(258).rstrip("\r\n")
    minimum = 0 if allow_empty else 8
    if not minimum <= len(secret) <= 256 or contains_control_characters(secret):
        raise PrinterManagerError(f"A senha deve ter entre {minimum} e 256 caracteres válidos.")
    return secret


def _authenticated_smb_uri(uri: str, username: str, password: str) -> str:
    safe_uri = validate_device_uri(uri)
    parsed = urlparse(safe_uri)
    if parsed.scheme.lower() != "smb" or parsed.username is not None:
        raise PrinterManagerError("A URI SMB autenticada deve chegar sem credenciais.")
    if not username or len(username) > 256 or contains_control_characters(username):
        raise PrinterManagerError("Usuário SMB inválido.")
    host = parsed.hostname or ""
    uri_host = f"[{host}]" if ":" in host else host
    if parsed.port is not None:
        uri_host = f"{uri_host}:{parsed.port}"
    userinfo = quote(username, safe="")
    if password:
        userinfo += f":{quote(password, safe='')}"
    return urlunparse(
        (
            parsed.scheme,
            f"{userinfo}@{uri_host}",
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def _add_printer_with_cups_api(queue: str, uri: str, model: str) -> int:
    """Envia a URI pelo protocolo IPP local, sem expô-la em ``argv``."""

    try:
        for key in tuple(os.environ):
            if key.startswith("CUPS_"):
                os.environ.pop(key)
        cups = importlib.import_module("cups")
        cups.setServer(local_cups_server())
        connection = cups.Connection()
        connection.addPrinter(queue, device=uri, ppdname=model)
        connection.enablePrinter(queue)
        connection.acceptJobs(queue)
    except (AttributeError, ImportError, RuntimeError) as exc:
        raise PrinterManagerError(
            f"A API Python do CUPS não está disponível ou recusou a operação: {redact_text(exc)}"
        ) from exc
    except Exception as exc:
        # ``cups.IPPError`` não possui tipo estável para anotação sem tornar
        # pycups uma dependência do ambiente de desenvolvimento.
        raise PrinterManagerError(f"O CUPS recusou a fila: {redact_text(exc)}") from exc
    return 0


def _atomic_samba_config(content: str) -> None:
    SAMBA_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    previous = (
        SAMBA_CONFIG.read_text(encoding="utf-8", errors="replace") if SAMBA_CONFIG.exists() else ""
    )
    stat = SAMBA_CONFIG.stat() if SAMBA_CONFIG.exists() else None
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=SAMBA_CONFIG.parent,
        prefix=".smb.conf.neri-",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        temporary.chmod(stat.st_mode & 0o777 if stat else 0o644)
        if stat:
            os.chown(temporary, stat.st_uid, stat.st_gid)
        try:
            validator = subprocess.run(
                ["/usr/bin/testparm", "-s", str(temporary)],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
                env=COMMAND_ENV,
            )
        except subprocess.TimeoutExpired as exc:
            raise PrinterManagerError("O Samba não concluiu a validação da configuração.") from exc
        if validator.returncode != 0:
            raise PrinterManagerError(
                validator.stderr or validator.stdout or "Configuração Samba inválida."
            )
        if SAMBA_CONFIG.exists():
            backup = SAMBA_CONFIG.with_name("smb.conf.neri.bak")
            if not backup.exists():
                shutil.copy2(SAMBA_CONFIG, backup)
        os.replace(temporary, SAMBA_CONFIG)
    except Exception:
        temporary.unlink(missing_ok=True)
        if not SAMBA_CONFIG.exists() and previous:
            SAMBA_CONFIG.write_text(previous, encoding="utf-8")
        raise


def _upsert_samba_section(lines: list[str], section: str, managed: dict[str, str]) -> list[str]:
    """Atualiza apenas diretivas gerenciadas e preserva o restante do smb.conf."""

    section_pattern = re.compile(rf"\s*\[{re.escape(section)}\]\s*", re.IGNORECASE)
    start = next(
        (index for index, line in enumerate(lines) if section_pattern.fullmatch(line)),
        None,
    )
    if start is None:
        if section.casefold() == "global":
            lines[0:0] = ["[global]", ""]
            start = 0
        else:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(f"[{section}]")
            start = len(lines) - 1
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if re.fullmatch(r"\s*\[[^]]+\]\s*", lines[index])
        ),
        len(lines),
    )
    for key, value in managed.items():
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=", re.IGNORECASE)
        existing = [index for index in range(start + 1, end) if pattern.match(lines[index])]
        directive = f"   {key} = {value}"
        if not existing:
            lines.insert(end, directive)
            end += 1
        else:
            lines[existing[0]] = directive
            for duplicate in reversed(existing[1:]):
                del lines[duplicate]
                end -= 1
    return lines


def _ensure_samba_printers_section() -> None:
    text = (
        SAMBA_CONFIG.read_text(encoding="utf-8", errors="replace")
        if SAMBA_CONFIG.exists()
        else "[global]\n"
    )
    global_managed = {
        "printing": "cups",
        "printcap name": "cups",
        "load printers": "yes",
    }
    printers_managed = {
        "comment": "Impressoras compartilhadas",
        "path": "/var/spool/samba",
        "printable": "yes",
        "browseable": "yes",
        "guest ok": "no",
        "read only": "yes",
        "use client driver": "yes",
        "create mask": "0700",
    }
    lines = text.rstrip().splitlines()
    lines = _upsert_samba_section(lines, "global", global_managed)
    lines = _upsert_samba_section(lines, "printers", printers_managed)
    _atomic_samba_config("\n".join(lines) + "\n")


def _enable_printer_sharing(name: str) -> int:
    queue = validate_queue_name(name)
    if not _queue_exists(queue):
        raise PrinterManagerError("A fila selecionada não existe no CUPS.")
    _ensure_samba_printers_section()
    SAMBA_SPOOL.mkdir(parents=True, exist_ok=True)
    SAMBA_SPOOL.chmod(0o1777)
    commands = (
        ["/usr/sbin/lpadmin", "-p", queue, "-o", "printer-is-shared=true"],
        [
            "/usr/sbin/cupsctl",
            "--no-remote-any",
            "--no-remote-admin",
            "--share-printers",
        ],
        ["/usr/bin/systemctl", "enable", "--now", "cups.service"],
        ["/usr/bin/systemctl", "enable", "--now", "smbd.service"],
    )
    for command in commands:
        result = _execute(command)
        if result:
            _execute(["/usr/sbin/lpadmin", "-p", queue, "-o", "printer-is-shared=false"])
            return result
    return 0


def _disable_printer_sharing(name: str) -> int:
    queue = validate_queue_name(name)
    if not _queue_exists(queue):
        raise PrinterManagerError("A fila selecionada não existe no CUPS.")
    return _execute(["/usr/sbin/lpadmin", "-p", queue, "-o", "printer-is-shared=false"])


def _caller() -> pwd.struct_passwd:
    raw_uid = os.environ.get("PKEXEC_UID", "")
    if not raw_uid.isdigit():
        raise PrinterManagerError("Não foi possível identificar o usuário solicitante.")
    account = pwd.getpwuid(int(raw_uid))
    if account.pw_uid == 0:
        raise PrinterManagerError("A operação deve ser solicitada por um usuário comum.")
    return account


def _configure_samba_password(username: str) -> int:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username):
        raise PrinterManagerError("Nome de usuário local inválido.")
    account = pwd.getpwnam(username)
    caller = _caller()
    if account.pw_uid == 0 or account.pw_uid < 1000:
        raise PrinterManagerError("Escolha uma conta de usuário comum existente.")
    if caller.pw_uid != account.pw_uid:
        raise PrinterManagerError("A senha Samba só pode ser configurada para o usuário atual.")
    password = _stdin_secret()
    return _execute(
        ["/usr/bin/smbpasswd", "-s", "-a", username],
        input_text=f"{password}\n{password}\n",
    )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _allowed_backup_destination(destination: str) -> tuple[Path, pwd.struct_passwd]:
    account = _caller()
    target = Path(destination).expanduser().resolve(strict=True)
    roots = [Path(account.pw_dir).resolve()]
    for candidate in (Path("/media") / account.pw_name, Path("/run/media") / account.pw_name):
        if candidate.exists():
            roots.append(candidate.resolve())
    if (
        not target.is_dir()
        or target.is_symlink()
        or not any(_is_within(target, root) for root in roots)
    ):
        raise PrinterManagerError(
            "Escolha uma pasta dentro da sua pasta pessoal ou de uma mídia montada para o usuário."
        )
    return target, account


def _sha256_stream(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    reader = handle.read
    for chunk in iter(lambda: reader(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _exclusive_path(folder: Path, stem: str, suffix: str) -> tuple[Path, int]:
    for index in range(100):
        marker = "" if index == 0 else f"-{index}"
        candidate = folder / f"{stem}{marker}{suffix}"
        try:
            descriptor = os.open(
                candidate,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            return candidate, descriptor
        except FileExistsError:
            continue
    raise PrinterManagerError("Não foi possível criar um nome único para o backup.")


def _create_backup(destination: str) -> int:
    folder, account = _allowed_backup_destination(destination)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive, descriptor = _exclusive_path(folder, f"neri-printer-backup-{stamp}", ".tar.gz")
    existing = [source for source in BACKUP_SOURCES if source.exists()]
    manifest: Path | None = None
    try:
        with os.fdopen(descriptor, "w+b") as output:
            with tarfile.open(fileobj=output, mode="w:gz") as bundle:
                for source in existing:
                    bundle.add(source, arcname=str(source).lstrip("/"), recursive=True)
            output.flush()
            os.fsync(output.fileno())
            output.seek(0)
            checksum = _sha256_stream(output)
            os.fchown(output.fileno(), account.pw_uid, account.pw_gid)
        manifest, manifest_descriptor = _exclusive_path(folder, archive.name, ".json")
        payload = {
            "created_at": stamp,
            "archive": archive.name,
            "sha256": checksum,
            "sources": [str(source) for source in existing],
        }
        with os.fdopen(manifest_descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
            os.fchown(output.fileno(), account.pw_uid, account.pw_gid)
        print(json.dumps({**payload, "archive_path": str(archive), "manifest_path": str(manifest)}))
        return 0
    except Exception:
        archive.unlink(missing_ok=True)
        if manifest is not None:
            manifest.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    if os.geteuid() != 0:
        return _fail("Execute este componente via PolicyKit.")
    if len(arguments) < 2:
        return _fail("Ação não informada.")
    action, *values = arguments[1:]
    try:
        if action == "add" and len(values) == 3:
            with _queue_creation_lock():
                queue = _ensure_new_queue(values[0])
                uri = validate_device_uri(values[1])
                if urlparse(uri).username is not None:
                    raise PrinterManagerError("Use a ação SMB autenticada.")
                result = _execute(
                    [
                        "/usr/sbin/lpadmin",
                        "-p",
                        queue,
                        "-E",
                        "-v",
                        uri,
                        "-m",
                        validate_driver_model(values[2]),
                    ]
                )
                if result:
                    _cleanup_failed_queue(queue)
                return result
        if action == "add-smb" and len(values) == 4:
            with _queue_creation_lock():
                queue = _ensure_new_queue(values[0])
                uri = _authenticated_smb_uri(values[1], values[3], _stdin_secret(allow_empty=True))
                try:
                    return _add_printer_with_cups_api(
                        queue,
                        uri,
                        validate_driver_model(values[2]),
                    )
                except PrinterManagerError:
                    _cleanup_failed_queue(queue)
                    raise
        if action == "remove" and len(values) == 1:
            with _queue_creation_lock():
                return _execute(["/usr/sbin/lpadmin", "-x", validate_queue_name(values[0])])
        if action == "pause" and len(values) == 1:
            return _execute(["/usr/sbin/cupsdisable", validate_queue_name(values[0])])
        if action == "resume" and len(values) == 1:
            queue = validate_queue_name(values[0])
            return _execute(["/usr/sbin/cupsenable", queue]) or _execute(
                ["/usr/sbin/cupsaccept", queue]
            )
        if action == "cancel-job" and len(values) == 1:
            return _execute(["/usr/bin/cancel", validate_job_id(values[0])])
        if action == "install-packages" and values:
            return _install_packages(values)
        if action == "reinstall-packages" and values:
            return _install_packages(values, reinstall=True)
        if action == "restart-cups" and not values:
            return _execute(["/usr/bin/systemctl", "restart", "cups.service"])
        if action == "enable-service" and len(values) == 1:
            return _enable_service(values[0])
        if action == "clear-jobs" and not values:
            return _execute(["/usr/bin/cancel", "-a"])
        if action == "fix-cups-permissions" and not values:
            return _fix_cups_permissions()
        if action == "enable-printer-sharing" and len(values) == 1:
            return _enable_printer_sharing(values[0])
        if action == "disable-printer-sharing" and len(values) == 1:
            return _disable_printer_sharing(values[0])
        if action == "set-samba-password" and len(values) == 1:
            return _configure_samba_password(values[0])
        if action == "create-backup" and len(values) == 1:
            return _create_backup(values[0])
    except (KeyError, OSError, PrinterManagerError, ValueError) as exc:
        return _fail(exc)
    return _fail("Ação ou argumentos não permitidos.")


if __name__ == "__main__":
    raise SystemExit(main())
