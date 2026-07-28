import pytest

from neri_printer_manager import core
from neri_printer_manager.core import (
    CommandResult,
    CommandRunner,
    CupsService,
    DiagnosticItem,
    DiscoveryService,
    Printer,
    PrinterManagerError,
    Severity,
    validate_device_uri,
    validate_driver_model,
    validate_job_id,
    validate_queue_name,
    write_report,
)


def test_safe_queue_name() -> None:
    assert validate_queue_name("RECEPCAO-01") == "RECEPCAO-01"


@pytest.mark.parametrize("value", ["", "fila com espaço", "x;rm", "a/b"])
def test_unsafe_queue_names_are_rejected(value: str) -> None:
    with pytest.raises(PrinterManagerError):
        validate_queue_name(value)


@pytest.mark.parametrize(
    "value",
    [
        "ipp://printer.local/ipp/print",
        "socket://10.0.0.5:9100",
        "smb://server/printer",
        "hp:/usb/HP_LaserJet_Pro?serial=ABC123",
    ],
)
def test_supported_device_uris(value: str) -> None:
    assert validate_device_uri(value) == value


def test_unknown_device_protocol_is_rejected() -> None:
    with pytest.raises(PrinterManagerError):
        validate_device_uri("file:///tmp/output")


@pytest.mark.parametrize(
    "value",
    [
        "socket://10.0.0.5",
        "smb://server",
        "ipp://user:secret@printer.local/ipp/print",
        "ipp://printer.local/ipp/print%0aevil",
        "ipp://printer.local/ipp/print%09evil",
        "ipp://printer local/ipp/print",
        "hp:/net/HP_LaserJet_Pro",
    ],
)
def test_incomplete_or_unsafe_device_uris_are_rejected(value: str) -> None:
    with pytest.raises(PrinterManagerError):
        validate_device_uri(value)


@pytest.mark.parametrize("value", ["", "../driver", "everywhere;reboot", "driver name"])
def test_unsafe_driver_identifiers_are_rejected(value: str) -> None:
    with pytest.raises(PrinterManagerError):
        validate_driver_model(value)


def test_valid_job_id() -> None:
    assert validate_job_id("RECEPCAO-42") == "RECEPCAO-42"


@pytest.mark.parametrize("value", ["", "42", "fila 1", "fila-1;rm"])
def test_invalid_job_id_is_rejected(value: str) -> None:
    with pytest.raises(PrinterManagerError):
        validate_job_id(value)


def test_command_runner_captures_output() -> None:
    result = CommandRunner().run(["python3", "-c", "print('ok')"])
    assert result.stdout == "ok"
    assert result.returncode == 0


class CupsRunner:
    def run(self, args, **_kwargs):
        command = tuple(args)
        outputs = {
            ("lpstat", "-p"): CommandResult(
                command,
                0,
                "printer LOCAL is idle\nprinter REMOTA is idle",
                "",
            ),
            ("lpstat", "-a"): CommandResult(
                command,
                0,
                "LOCAL accepting requests\nREMOTA accepting requests",
                "",
            ),
            ("lpstat", "-v"): CommandResult(
                command,
                0,
                "device for LOCAL: ipp://10.0.0.5/ipp/print\n"
                "device for REMOTA: implicitclass://REMOTA/",
                "",
            ),
        }
        return outputs[command]


def test_automatic_cups_browsed_queues_are_not_treated_as_installed() -> None:
    cups = CupsService(CupsRunner())  # type: ignore[arg-type]
    assert [printer.name for printer in cups.list_printers()] == ["LOCAL"]
    all_printers = cups.list_printers(include_automatic=True)
    assert [printer.name for printer in all_printers] == ["LOCAL", "REMOTA"]
    assert all_printers[-1].automatic is True


def test_queue_collision_check_is_case_insensitive() -> None:
    cups = CupsService(CupsRunner())  # type: ignore[arg-type]
    assert cups.queue_exists("local") is True


class AdminRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str | None]] = []

    def run(self, args, **kwargs):
        self.calls.append((list(args), kwargs.get("input_text")))
        return CommandResult(tuple(args), 0, "", "")


def test_authenticated_smb_password_is_not_a_pkexec_argument(monkeypatch, tmp_path) -> None:
    helper = tmp_path / "helper"
    helper.write_text("helper", encoding="utf-8")
    monkeypatch.setattr(core, "ADMIN_HELPER", helper)
    runner = AdminRunner()
    cups = CupsService(runner)  # type: ignore[arg-type]
    cups.add_authenticated_printer(
        "FILA",
        "smb://10.0.0.8/HP",
        "drv:///sample.drv/generic.ppd",
        "DOMINIO\\same",
        "segredo",
    )
    arguments, input_text = runner.calls[0]
    assert arguments[2] == "add-smb"
    assert all("segredo" not in argument for argument in arguments)
    assert input_text == "segredo\n"


def test_generic_add_rejects_credentials_in_uri() -> None:
    with pytest.raises(PrinterManagerError, match="fluxo autenticado"):
        CupsService(AdminRunner()).add_printer(  # type: ignore[arg-type]
            "FILA",
            "smb://user:secret@server/HP",
            "drv:///sample.drv/generic.ppd",
        )


def test_legacy_report_writer_redacts_authenticated_uris(tmp_path) -> None:
    path = tmp_path / "report.json"
    write_report(
        path,
        [
            Printer(
                "FILA",
                "idle",
                True,
                True,
                "smb://usuario:segredo@servidor/FILA",
            )
        ],
        [DiagnosticItem("ok", "Teste", Severity.OK, "password=nao-vazar")],
    )
    content = path.read_text(encoding="utf-8")
    assert "segredo" not in content
    assert "nao-vazar" not in content


def test_basic_discovery_ignores_lpinfo_backend_placeholders() -> None:
    class Runner:
        @staticmethod
        def exists(_command: str) -> bool:
            return True

        @staticmethod
        def run(args, **_kwargs):
            return CommandResult(
                tuple(args),
                0,
                "network ipp\nnetwork socket\ndirect usb://HP/LaserJet\n",
                "",
            )

    devices = DiscoveryService(Runner()).discover()  # type: ignore[arg-type]
    assert [item.uri for item in devices] == ["usb://HP/LaserJet"]
