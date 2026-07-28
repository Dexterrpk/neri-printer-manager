import subprocess
from io import StringIO
from types import SimpleNamespace

import pytest

from neri_printer_manager import privileged
from neri_printer_manager.core import PrinterManagerError


def test_helper_refuses_to_run_without_root(monkeypatch) -> None:
    monkeypatch.setattr(privileged.os, "geteuid", lambda: 1000)
    assert privileged.main(["helper", "restart-cups"]) == 2


def test_helper_rejects_queue_collision_before_lpadmin(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(privileged.os, "geteuid", lambda: 0)
    monkeypatch.setattr(privileged.os, "fchown", lambda *_args: None)
    monkeypatch.setattr(privileged, "QUEUE_LOCK", tmp_path / "queue.lock")
    monkeypatch.setattr(privileged, "_queue_exists", lambda _name: True)
    monkeypatch.setattr(
        privileged,
        "_execute",
        lambda command, **_kwargs: calls.append(command) or 0,
    )
    result = privileged.main(["helper", "add", "FILA", "ipp://10.0.0.5/ipp/print", "everywhere"])
    assert result == 2
    assert calls == []


def test_smb_password_enters_through_stdin_not_helper_arguments(monkeypatch, tmp_path) -> None:
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(privileged.os, "geteuid", lambda: 0)
    monkeypatch.setattr(privileged.os, "fchown", lambda *_args: None)
    monkeypatch.setattr(privileged, "QUEUE_LOCK", tmp_path / "queue.lock")
    monkeypatch.setattr(privileged, "_queue_exists", lambda _name: False)
    monkeypatch.setattr(privileged.sys, "stdin", StringIO("senha com espaço\n"))
    monkeypatch.setattr(
        privileged,
        "_add_printer_with_cups_api",
        lambda queue, uri, model: calls.append((queue, uri, model)) or 0,
    )
    arguments = [
        "helper",
        "add-smb",
        "FILA",
        "smb://10.0.0.8/HP",
        "drv:///sample.drv/generic.ppd",
        "DOMINIO\\same",
    ]
    assert all("senha" not in value for value in arguments)
    assert privileged.main(arguments) == 0
    assert "DOMINIO%5Csame:senha%20com%20espa%C3%A7o@" in calls[0][1]


def test_cups_api_receives_the_device_uri_without_a_child_process(monkeypatch) -> None:
    events: list[tuple[object, ...]] = []

    class Connection:
        def addPrinter(self, queue, **options):
            events.append(("add", queue, options))

        def enablePrinter(self, queue):
            events.append(("enable", queue))

        def acceptJobs(self, queue):
            events.append(("accept", queue))

    class CupsModule:
        @staticmethod
        def setServer(server):
            events.append(("server", server))

        @staticmethod
        def Connection():
            return Connection()

    monkeypatch.setattr(privileged.importlib, "import_module", lambda _name: CupsModule())
    assert (
        privileged._add_printer_with_cups_api(
            "FILA",
            "smb://user:secret@server/HP",
            "drv:///sample.drv/generic.ppd",
        )
        == 0
    )
    assert events[-3] == (
        "add",
        "FILA",
        {
            "device": "smb://user:secret@server/HP",
            "ppdname": "drv:///sample.drv/generic.ppd",
        },
    )
    assert events[-2:] == [("enable", "FILA"), ("accept", "FILA")]


def test_samba_sharing_does_not_enable_remote_any(monkeypatch, tmp_path) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(privileged, "SAMBA_CONFIG", tmp_path / "smb.conf")
    monkeypatch.setattr(privileged, "SAMBA_SPOOL", tmp_path / "spool")
    monkeypatch.setattr(privileged, "_queue_exists", lambda _name: True)
    monkeypatch.setattr(privileged, "_ensure_samba_printers_section", lambda: None)
    monkeypatch.setattr(
        privileged,
        "_execute",
        lambda command, **_kwargs: commands.append(command) or 0,
    )
    assert privileged._enable_printer_sharing("FILA") == 0
    cupsctl = next(command for command in commands if command[0] == "/usr/sbin/cupsctl")
    assert "--share-printers" in cupsctl
    assert "--no-remote-any" in cupsctl
    assert "--no-remote-admin" in cupsctl
    assert "--remote-any" not in cupsctl


def test_existing_samba_printers_section_is_hardened(monkeypatch, tmp_path) -> None:
    config = tmp_path / "smb.conf"
    config.write_text(
        "[global]\n   workgroup = WORKGROUP\n\n"
        "[printers]\n   guest ok = yes\n   guest ok = yes\n   printable = no\n\n"
        "[dados]\n   path = /srv/dados\n",
        encoding="utf-8",
    )
    captured: list[str] = []
    monkeypatch.setattr(privileged, "SAMBA_CONFIG", config)
    monkeypatch.setattr(privileged, "_atomic_samba_config", captured.append)
    privileged._ensure_samba_printers_section()
    assert len(captured) == 1
    content = captured[0]
    assert content.lower().count("guest ok") == 1
    assert "guest ok = no" in content
    assert "printable = yes" in content
    assert "printing = cups" in content
    assert "printcap name = cups" in content
    assert "load printers = yes" in content
    assert "[dados]\n   path = /srv/dados" in content


def test_package_allowlist_is_checked_before_apt_update(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        privileged,
        "_execute",
        lambda command, **_kwargs: calls.append(command) or 0,
    )
    with pytest.raises(PrinterManagerError, match="não autorizado"):
        privileged._install_packages(["pacote-injetado"])
    assert calls == []


def test_queue_lookup_is_case_insensitive(monkeypatch) -> None:
    monkeypatch.setattr(
        privileged.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="printer RECEPCAO is idle\n",
            stderr="",
        ),
    )
    assert privileged._queue_exists("recepcao") is True


def test_queue_lookup_fails_closed_when_cups_does_not_respond(monkeypatch) -> None:
    monkeypatch.setattr(
        privileged.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="lpstat: Scheduler is not running.",
        ),
    )
    with pytest.raises(PrinterManagerError, match="confirmar"):
        privileged._queue_exists("FILA")


def test_execute_has_a_timeout(monkeypatch) -> None:
    def expire(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(privileged.subprocess, "run", expire)
    assert privileged._execute(["/usr/bin/systemctl", "status"], timeout=1) == 124


def test_samba_username_is_revalidated_by_the_helper() -> None:
    with pytest.raises(PrinterManagerError, match="usuário local inválido"):
        privileged._configure_samba_password("usuario\nmalicioso")
