import socket

import pytest

from neri_printer_manager.core import CommandResult, PrinterManagerError
from neri_printer_manager.host_locator import HostPrinterLocator, ResolvedHost
from neri_printer_manager.network import PortCheck, PortState


class FakeRunner:
    def __init__(self, outputs: dict[tuple[str, ...], CommandResult] | None = None) -> None:
        self.outputs = outputs or {}

    @staticmethod
    def exists(command: str) -> bool:
        return command in {"getent", "avahi-resolve-host-name", "nmblookup", "smbclient"}

    def run(self, args, *, privileged=False, check=True):
        key = tuple(args)
        return self.outputs.get(key, CommandResult(key, 1, "", ""))


def _ports(host: str, *, ipp=False, jetdirect=False, lpd=False, smb=False):
    return [
        PortCheck(host, 631, "IPP/CUPS", PortState.OPEN if ipp else PortState.CLOSED, ""),
        PortCheck(
            host, 9100, "JetDirect/AppSocket", PortState.OPEN if jetdirect else PortState.CLOSED, ""
        ),
        PortCheck(host, 515, "LPD", PortState.OPEN if lpd else PortState.CLOSED, ""),
        PortCheck(host, 445, "SMB", PortState.OPEN if smb else PortState.CLOSED, ""),
        PortCheck(host, 139, "NetBIOS/SMB", PortState.CLOSED, ""),
    ]


def test_normalize_windows_run_style_host() -> None:
    assert HostPrinterLocator.normalize_host(r"\\PC-RECEPCAO") == "PC-RECEPCAO"


def test_normalize_smb_url() -> None:
    assert HostPrinterLocator.normalize_host("smb://PC-RECEPCAO/HP") == "pc-recepcao"


def test_resolve_with_netbios_when_dns_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *args, **kwargs: (_ for _ in ()).throw(socket.gaierror())
    )
    runner = FakeRunner(
        {
            ("nmblookup", "PC-RECEPCAO"): CommandResult(
                ("nmblookup", "PC-RECEPCAO"), 0, "10.3.45.22 PC-RECEPCAO<00>", ""
            )
        }
    )
    resolved = HostPrinterLocator(runner).resolve("PC-RECEPCAO")
    assert resolved.address == "10.3.45.22"
    assert resolved.method == "NetBIOS"


def test_resolve_with_avahi(monkeypatch) -> None:
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *args, **kwargs: (_ for _ in ()).throw(socket.gaierror())
    )
    runner = FakeRunner(
        {
            ("avahi-resolve-host-name", "-4", "impressora.local"): CommandResult(
                ("avahi-resolve-host-name", "-4", "impressora.local"),
                0,
                "impressora.local 192.168.1.50",
                "",
            )
        }
    )
    resolved = HostPrinterLocator(runner).resolve("impressora")
    assert resolved.address == "192.168.1.50"
    assert resolved.method == "Avahi/mDNS"


def test_unknown_host_has_clear_error(monkeypatch) -> None:
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *args, **kwargs: (_ for _ in ()).throw(socket.gaierror())
    )
    with pytest.raises(PrinterManagerError, match="Não foi possível localizar"):
        HostPrinterLocator(FakeRunner()).resolve("NAO-EXISTE")


def test_ipp_is_recommended_before_jetdirect(monkeypatch) -> None:
    monkeypatch.setattr(
        HostPrinterLocator,
        "resolve",
        lambda self, host: ResolvedHost(host, "printer.local", "192.168.1.50", "DNS"),
    )
    monkeypatch.setattr(
        "neri_printer_manager.host_locator.NetworkService.scan_printer_ports",
        lambda self, host: _ports(host, ipp=True, jetdirect=True),
    )
    results = HostPrinterLocator().locate("printer.local")
    assert [item.protocol for item in results] == ["IPP", "JetDirect"]
    assert results[0].recommended is True
    assert results[1].recommended is False


def test_jetdirect_is_recommended_when_ipp_is_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        HostPrinterLocator,
        "resolve",
        lambda self, host: ResolvedHost(host, "printer.local", "192.168.1.50", "DNS"),
    )
    monkeypatch.setattr(
        "neri_printer_manager.host_locator.NetworkService.scan_printer_ports",
        lambda self, host: _ports(host, jetdirect=True),
    )
    results = HostPrinterLocator().locate("printer.local")
    assert len(results) == 1
    assert results[0].protocol == "JetDirect"
    assert results[0].recommended is True


def test_missing_smbclient_does_not_hide_an_ipp_printer(monkeypatch) -> None:
    runner = FakeRunner()
    monkeypatch.setattr(runner, "exists", lambda name: name == "lpstat")
    monkeypatch.setattr(
        HostPrinterLocator,
        "resolve",
        lambda self, host: ResolvedHost(host, "printer.local", "192.168.1.50", "DNS"),
    )
    monkeypatch.setattr(
        "neri_printer_manager.host_locator.NetworkService.scan_printer_ports",
        lambda self, host: _ports(host, ipp=True, smb=True),
    )
    results = HostPrinterLocator(runner).locate("printer.local")
    assert [item.protocol for item in results] == ["IPP"]


def test_remote_cups_queues_are_enumerated_for_mint_to_mint(monkeypatch) -> None:
    command = ("lpstat", "-h", "192.168.1.60:631", "-e")
    runner = FakeRunner({command: CommandResult(command, 0, "RECEPCAO\nFINANCEIRO\n", "")})
    monkeypatch.setattr(runner, "exists", lambda name: name == "lpstat")
    monkeypatch.setattr(
        HostPrinterLocator,
        "resolve",
        lambda self, host: ResolvedHost(host, "mint-remoto.local", "192.168.1.60", "mDNS"),
    )
    monkeypatch.setattr(
        "neri_printer_manager.host_locator.NetworkService.scan_printer_ports",
        lambda self, host: _ports(host, ipp=True),
    )
    results = HostPrinterLocator(runner).locate("mint-remoto")
    assert [item.name for item in results] == ["RECEPCAO", "FINANCEIRO"]
    assert results[0].uri == "ipp://192.168.1.60:631/printers/RECEPCAO"
    assert "Linux Mint" in results[0].connection


def test_smb_discovery_accepts_printable_unicode_share_names() -> None:
    class SmbRunner(FakeRunner):
        @staticmethod
        def exists(command: str) -> bool:
            return command == "smbclient"

        def run(self, args, **_kwargs):
            command = tuple(args)
            return CommandResult(command, 0, "Printer|IMPRESSÃO RH|Fila do RH\n", "")

    resolved = ResolvedHost("pc-rh", "PC-RH", "192.168.1.70", "NetBIOS")
    items = HostPrinterLocator(SmbRunner())._smb_printers(
        resolved,
        "",
        "",
        recommended=True,
    )
    assert [item.name for item in items] == ["IMPRESSÃO RH"]
    assert items[0].uri == "smb://192.168.1.70/IMPRESS%C3%83O%20RH"
