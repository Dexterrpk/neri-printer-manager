import pytest

from neri_printer_manager.core import CommandResult, PrinterManagerError
from neri_printer_manager.host_locator import LocatedPrinter
from neri_printer_manager.smart_install import DriverCatalog, SmartPrinterInstaller


class FakeCups:
    def __init__(self, succeed_model: str) -> None:
        self.succeed_model = succeed_model
        self.calls: list[tuple[str, str, str]] = []
        self.auth_calls: list[tuple[str, str, str, str, str]] = []
        self.tested: list[str] = []
        self.removed: list[str] = []

    def add_printer(self, name: str, uri: str, model: str = "everywhere") -> None:
        self.calls.append((name, uri, model))
        if model != self.succeed_model:
            raise PrinterManagerError("modelo incompatível")

    def remove_printer(self, name: str) -> None:
        self.removed.append(name)

    def add_authenticated_printer(
        self,
        name: str,
        uri: str,
        model: str,
        username: str,
        password: str,
    ) -> None:
        self.auth_calls.append((name, uri, model, username, password))
        if model != self.succeed_model:
            raise PrinterManagerError("modelo incompatível")

    def resume(self, name: str) -> None:
        return None

    def print_test_page(self, name: str) -> None:
        self.tested.append(name)


class FakeRunner:
    def __init__(self, output: str) -> None:
        self.output = output

    def run(self, args, *, check=True, privileged=False):
        return CommandResult(tuple(args), 0, self.output, "")


def item(
    protocol: str, uri: str, *, name: str = "Teste", username: str = "", password: str = ""
) -> LocatedPrinter:
    return LocatedPrinter(
        name=name,
        host="MAQ211",
        address="192.168.1.65",
        connection="Rede",
        protocol=protocol,
        uri=uri,
        recommended=True,
        explanation="Teste",
        username=username,
        password=password,
    )


def empty_catalog() -> DriverCatalog:
    return DriverCatalog(FakeRunner(""))


def test_ipp_falls_back_to_generic_postscript() -> None:
    cups = FakeCups("drv:///sample.drv/generic.ppd")
    outcome = SmartPrinterInstaller(cups, catalog=empty_catalog()).install(
        "MAQ211",
        item("IPP", "ipp://192.168.1.65/ipp/print"),
    )
    assert outcome.description == "PostScript genérico"
    assert outcome.test_page_submitted is True
    assert cups.calls[0][2] == "everywhere"
    assert cups.calls[1][2] == "drv:///sample.drv/generic.ppd"


def test_smb_never_uses_everywhere() -> None:
    cups = FakeCups("drv:///sample.drv/generpcl.ppd")
    outcome = SmartPrinterInstaller(cups, catalog=empty_catalog()).install(
        "HP-RECEPCAO",
        item("SMB", "smb://192.168.1.65/HP-RECEPCAO"),
    )
    assert outcome.description == "PCL genérico"
    assert all(model != "everywhere" for _, _, model in cups.calls)


def test_exact_driver_is_prioritized() -> None:
    output = """drv:///hp/hpcups.drv/hp-laserjet_pro_m402.ppd HP LaserJet Pro M402, hpcups
    drv:///sample.drv/generpcl.ppd Generic PCL Laser Printer
    """
    cups = FakeCups("drv:///hp/hpcups.drv/hp-laserjet_pro_m402.ppd")
    catalog = DriverCatalog(FakeRunner(output))
    outcome = SmartPrinterInstaller(cups, catalog=catalog).install(
        "HP-M402",
        item("SMB", "smb://192.168.1.65/HP-M402", name="HP LaserJet Pro M402"),
    )
    assert outcome.model == "drv:///hp/hpcups.drv/hp-laserjet_pro_m402.ppd"
    assert cups.calls[0][2] == outcome.model


def test_smb_credentials_use_the_dedicated_secure_flow() -> None:
    cups = FakeCups("drv:///sample.drv/generic.ppd")
    printer = item(
        "SMB",
        "smb://192.168.1.65/HP-RECEPCAO",
        username="DOMINIO\\same",
        password="senha com espaço",
    )
    SmartPrinterInstaller(cups, catalog=empty_catalog()).install("HP-RECEPCAO", printer)
    assert not cups.calls
    assert cups.auth_calls[-1][1] == "smb://192.168.1.65/HP-RECEPCAO"
    assert cups.auth_calls[-1][3:] == ("DOMINIO\\same", "senha com espaço")
    assert "senha" not in cups.auth_calls[-1][1]


def test_failed_attempts_never_trigger_blind_queue_removal() -> None:
    cups = FakeCups("modelo-que-nao-existe")
    with pytest.raises(PrinterManagerError):
        SmartPrinterInstaller(cups, catalog=empty_catalog()).install(
            "FILA",
            item("IPP", "ipp://192.168.1.65/ipp/print"),
        )
    assert cups.removed == []


def test_queue_created_by_this_attempt_is_cleaned_after_verification_failure() -> None:
    class VerificationFailure(FakeCups):
        def verify_printer(self, _name: str) -> None:
            raise PrinterManagerError("fila não apareceu")

    cups = VerificationFailure("everywhere")
    with pytest.raises(PrinterManagerError):
        SmartPrinterInstaller(cups, catalog=empty_catalog()).install(
            "FILA",
            item("IPP", "ipp://192.168.1.65/ipp/print"),
        )
    assert cups.removed == ["FILA"]
