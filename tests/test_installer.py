import pytest

from neri_printer_manager.core import CommandResult, PrinterManagerError
from neri_printer_manager.installer import SmartInstallService


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, args, *, privileged=False, check=True):
        command = list(args)
        self.calls.append(command)
        if command[:2] == ["lpinfo", "-m"]:
            return CommandResult(
                tuple(command),
                0,
                "drv:///sample.drv/generpcl.ppd Generic PCL Laser Printer",
                "",
            )
        return CommandResult(tuple(command), 0, "", "")


class FakeCups:
    def __init__(self) -> None:
        self.runner = FakeRunner()
        self.attempts: list[tuple[str, str, str]] = []

    def add_printer(self, name: str, uri: str, model: str = "everywhere") -> None:
        self.attempts.append((name, uri, model))
        if model == "everywhere":
            raise PrinterManagerError(
                "lpadmin: Unable to create PPD: Printer does not support required IPP attributes or document formats."
            )


def test_falls_back_to_generic_pcl_when_everywhere_is_not_supported(monkeypatch) -> None:
    cups = FakeCups()
    service = SmartInstallService(cups)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_port_open", lambda host, port: False)

    result = service.install("HP_M402", "ipp://10.0.0.20/ipp/print")

    assert result.automatic_fallback is True
    assert result.model == "drv:///sample.drv/generpcl.ppd"
    assert cups.attempts[-1] == (
        "HP_M402",
        "ipp://10.0.0.20/ipp/print",
        "drv:///sample.drv/generpcl.ppd",
    )


def test_non_driverless_error_is_not_hidden() -> None:
    class BrokenCups(FakeCups):
        def add_printer(self, name: str, uri: str, model: str = "everywhere") -> None:
            raise PrinterManagerError("Permission denied")

    with pytest.raises(PrinterManagerError, match="Permission denied"):
        SmartInstallService(BrokenCups()).install("FILA", "ipp://10.0.0.20/ipp/print")  # type: ignore[arg-type]
