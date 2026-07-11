import pytest

from neri_printer_manager.network import NetworkService, PortState


def test_validate_ip_and_hostname() -> None:
    assert NetworkService.validate_host("192.168.1.50") == "192.168.1.50"
    assert NetworkService.validate_host("printer.local") == "printer.local"


@pytest.mark.parametrize("value", ["", "host com espaço", "bad/host", ".local"])
def test_invalid_hosts_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        NetworkService.validate_host(value)


def test_unknown_port_is_not_scanned() -> None:
    result = NetworkService().check_port("127.0.0.1", 22)
    assert result.state is PortState.INVALID
