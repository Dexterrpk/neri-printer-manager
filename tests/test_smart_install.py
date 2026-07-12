from neri_printer_manager.core import PrinterManagerError
from neri_printer_manager.host_locator import LocatedPrinter
from neri_printer_manager.smart_install import SmartPrinterInstaller


class FakeCups:
    def __init__(self, succeed_model: str) -> None:
        self.succeed_model = succeed_model
        self.calls: list[tuple[str, str, str]] = []

    def add_printer(self, name: str, uri: str, model: str = "everywhere") -> None:
        self.calls.append((name, uri, model))
        if model != self.succeed_model:
            raise PrinterManagerError("modelo incompatível")

    def remove_printer(self, name: str) -> None:
        return None


def item(protocol: str, uri: str) -> LocatedPrinter:
    return LocatedPrinter(
        name="Teste",
        host="MAQ211",
        address="192.168.1.65",
        connection="Rede",
        protocol=protocol,
        uri=uri,
        recommended=True,
        explanation="Teste",
    )


def test_ipp_falls_back_to_generic_postscript() -> None:
    cups = FakeCups("drv:///sample.drv/generic.ppd")
    outcome = SmartPrinterInstaller(cups).install(
        "MAQ211",
        item("IPP", "ipp://192.168.1.65/ipp/print"),
    )
    assert outcome.description == "PostScript genérico"
    assert cups.calls[0][2] == "everywhere"
    assert cups.calls[1][2] == "drv:///sample.drv/generic.ppd"


def test_smb_never_uses_everywhere() -> None:
    cups = FakeCups("drv:///sample.drv/generpcl.ppd")
    outcome = SmartPrinterInstaller(cups).install(
        "HP-RECEPCAO",
        item("SMB", "smb://192.168.1.65/HP-RECEPCAO"),
    )
    assert outcome.description == "PCL genérico"
    assert all(model != "everywhere" for _, _, model in cups.calls)
