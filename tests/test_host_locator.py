from neri_printer_manager.host_locator import HostPrinterLocator
from neri_printer_manager.network import PortCheck, PortState


def test_ipp_is_recommended_before_jetdirect(monkeypatch) -> None:
    monkeypatch.setattr(HostPrinterLocator, "resolve", staticmethod(lambda host: ("printer.local", "192.168.1.50")))
    monkeypatch.setattr(
        "neri_printer_manager.host_locator.NetworkService.scan_printer_ports",
        lambda self, host: [
            PortCheck(host, 631, "IPP/CUPS", PortState.OPEN, "Respondendo"),
            PortCheck(host, 9100, "JetDirect/AppSocket", PortState.OPEN, "Respondendo"),
            PortCheck(host, 515, "LPD", PortState.CLOSED, "Fechada"),
            PortCheck(host, 445, "SMB", PortState.CLOSED, "Fechada"),
            PortCheck(host, 139, "NetBIOS/SMB", PortState.CLOSED, "Fechada"),
        ],
    )
    results = HostPrinterLocator().locate("printer.local")
    assert [item.protocol for item in results] == ["IPP", "JetDirect"]
    assert results[0].recommended is True
    assert results[1].recommended is False


def test_jetdirect_is_recommended_when_ipp_is_closed(monkeypatch) -> None:
    monkeypatch.setattr(HostPrinterLocator, "resolve", staticmethod(lambda host: ("printer.local", "192.168.1.50")))
    monkeypatch.setattr(
        "neri_printer_manager.host_locator.NetworkService.scan_printer_ports",
        lambda self, host: [
            PortCheck(host, 631, "IPP/CUPS", PortState.CLOSED, "Fechada"),
            PortCheck(host, 9100, "JetDirect/AppSocket", PortState.OPEN, "Respondendo"),
            PortCheck(host, 515, "LPD", PortState.CLOSED, "Fechada"),
            PortCheck(host, 445, "SMB", PortState.CLOSED, "Fechada"),
            PortCheck(host, 139, "NetBIOS/SMB", PortState.CLOSED, "Fechada"),
        ],
    )
    results = HostPrinterLocator().locate("printer.local")
    assert len(results) == 1
    assert results[0].protocol == "JetDirect"
    assert results[0].recommended is True
