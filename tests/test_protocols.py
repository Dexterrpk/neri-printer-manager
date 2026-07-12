from neri_printer_manager.network import PortCheck, PortState
from neri_printer_manager.protocols import ProtocolAdvisor


class FakeNetwork:
    def scan_printer_ports(self, host: str):
        return [
            PortCheck(host, 631, "IPP/CUPS", PortState.OPEN, "ok"),
            PortCheck(host, 9100, "JetDirect/AppSocket", PortState.OPEN, "ok"),
            PortCheck(host, 515, "LPD", PortState.CLOSED, "closed"),
            PortCheck(host, 445, "SMB", PortState.CLOSED, "closed"),
            PortCheck(host, 139, "NetBIOS/SMB", PortState.CLOSED, "closed"),
        ]


def test_ipp_is_preferred_when_available() -> None:
    recommendations = ProtocolAdvisor(FakeNetwork()).recommend_network("192.168.1.50")
    assert recommendations[0].protocol == "IPP"
    assert recommendations[0].uri == "ipp://192.168.1.50/ipp/print"
    assert recommendations[1].protocol == "JetDirect"


def test_windows_share_uri() -> None:
    recommendation = ProtocolAdvisor.windows_share("SERVIDOR", "HP_RECEPCAO")
    assert recommendation.uri == "smb://SERVIDOR/HP_RECEPCAO"
    assert recommendation.protocol == "SMB"
