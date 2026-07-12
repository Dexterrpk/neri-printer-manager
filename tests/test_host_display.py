from neri_printer_manager.core import PrinterManagerError
from neri_printer_manager.host_display import HostDisplayResolver


class TimeoutRunner:
    @staticmethod
    def exists(command: str) -> bool:
        return command == "nmblookup"

    def run(self, args, *, check=True):
        raise PrinterManagerError("timeout")


def test_netbios_timeout_does_not_break_discovery(monkeypatch):
    monkeypatch.setattr(HostDisplayResolver, "_reverse_dns", staticmethod(lambda address: ""))
    resolver = HostDisplayResolver(runner=TimeoutRunner())
    assert resolver.resolve("192.168.1.92", "192.168.1.92") == "Não identificado"


def test_existing_hostname_is_preserved():
    resolver = HostDisplayResolver(runner=TimeoutRunner())
    assert resolver.resolve("MAQ211", "192.168.1.65") == "MAQ211"
