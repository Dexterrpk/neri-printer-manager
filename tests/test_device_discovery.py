from neri_printer_manager.device_discovery import RichDiscoveryService


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


def test_safe_text_never_returns_empty_or_unbounded() -> None:
    assert RichDiscoveryService._safe_text("", "Desconhecido") == "Desconhecido"
    assert len(RichDiscoveryService._safe_text("x" * 500, "fallback", 40)) == 40
