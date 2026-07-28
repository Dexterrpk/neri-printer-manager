from neri_printer_manager.core import CommandResult
from neri_printer_manager.device_discovery import DiscoveredPrinter, RichDiscoveryService


class DiscoveryRunner:
    @staticmethod
    def exists(command: str) -> bool:
        return command == "lpinfo"

    def run(self, args, **_kwargs):
        command = tuple(args)
        return CommandResult(
            command,
            0,
            "network ipp\nnetwork socket\ndirect usb://HP/LaserJet\n",
            "",
        )


def test_parse_avahi_ipp_line() -> None:
    service = RichDiscoveryService()
    line = '=;eth0;IPv4;HP LaserJet M402dn;_ipp._tcp;local;hp-m402.local;192.168.1.80;631;"rp=ipp/print";"ty=HP LaserJet M402dn";"note=Recepção"'
    item = service._parse_avahi_line(line)
    assert item is not None
    assert item.name == "HP LaserJet M402dn"
    assert item.model == "HP LaserJet M402dn"
    assert item.host == "hp-m402.local"
    assert item.address == "192.168.1.80"
    assert item.protocol == "IPP"
    assert item.uri == "ipp://192.168.1.80:631/ipp/print"
    assert "Recepção" in item.location


def test_parse_avahi_rejects_invalid_port() -> None:
    service = RichDiscoveryService()
    line = '=;eth0;IPv4;Printer;_ipp._tcp;local;printer.local;192.168.1.50;invalid;"rp=ipp/print"'
    assert service._parse_avahi_line(line) is None


def test_parse_avahi_formats_ipv6_and_quotes_resource() -> None:
    service = RichDiscoveryService()
    line = '=;eth0;IPv6;Printer;_ipps._tcp;local;printer.local;2001:db8::20;443;"rp=ipp/My Printer"'
    item = service._parse_avahi_line(line)
    assert item is not None
    assert item.uri == "ipps://[2001:db8::20]:443/ipp/My%20Printer"


def test_parse_avahi_respects_escaped_field_separators() -> None:
    service = RichDiscoveryService()
    line = '=;eth0;IPv4;HP\\;Recepcao;_ipp._tcp;local;hp.local;192.168.1.80;631;"rp=ipp/print"'
    item = service._parse_avahi_line(line)
    assert item is not None
    assert item.name == "HP;Recepcao"


def test_lpinfo_backend_names_are_not_reported_as_phantom_devices() -> None:
    service = RichDiscoveryService(DiscoveryRunner())  # type: ignore[arg-type]
    devices = {}
    service._merge_lpinfo(devices, {})
    assert list(devices) == ["usb://HP/LaserJet"]


def test_uninstalled_usb_device_does_not_suppress_network_fallback() -> None:
    item = DiscoveredPrinter(
        "HP USB",
        "HP",
        "Este computador",
        "",
        "USB",
        "usb://HP/LaserJet",
        "Local",
    )
    assert RichDiscoveryService._is_remote_candidate(item) is False


def test_safe_text_never_returns_empty_or_unbounded() -> None:
    assert RichDiscoveryService._safe_text("", "Desconhecido") == "Desconhecido"
    assert len(RichDiscoveryService._safe_text("x" * 500, "fallback", 40)) == 40
