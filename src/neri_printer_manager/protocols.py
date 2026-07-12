"""Regras de recomendação de protocolo para instalação de impressoras."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .network import NetworkService, PortState


class ConnectionType(str, Enum):
    USB = "usb"
    NETWORK = "network"
    WINDOWS = "windows"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class ProtocolRecommendation:
    protocol: str
    uri: str
    title: str
    explanation: str
    confidence: int


class ProtocolAdvisor:
    """Sugere o protocolo mais adequado usando portas e tipo de conexão."""

    def __init__(self, network: NetworkService | None = None) -> None:
        self.network = network or NetworkService()

    def recommend_network(self, host: str) -> list[ProtocolRecommendation]:
        checks = {item.port: item for item in self.network.scan_printer_ports(host)}
        recommendations: list[ProtocolRecommendation] = []

        if checks[631].state is PortState.OPEN:
            recommendations.append(
                ProtocolRecommendation(
                    "IPP",
                    f"ipp://{host}/ipp/print",
                    "IPP — recomendado",
                    "Protocolo moderno, com melhor descoberta e suporte a impressão sem driver.",
                    100,
                )
            )
        if checks[9100].state is PortState.OPEN:
            recommendations.append(
                ProtocolRecommendation(
                    "JetDirect",
                    f"socket://{host}:9100",
                    "JetDirect — compatível",
                    "Conexão direta e rápida, comum em impressoras corporativas.",
                    85,
                )
            )
        if checks[515].state is PortState.OPEN:
            recommendations.append(
                ProtocolRecommendation(
                    "LPD",
                    f"lpd://{host}/lp",
                    "LPD — legado",
                    "Use quando IPP e JetDirect não estiverem disponíveis.",
                    60,
                )
            )
        if not recommendations:
            recommendations.extend(
                (
                    ProtocolRecommendation(
                        "IPP",
                        f"ipp://{host}/ipp/print",
                        "Tentar IPP",
                        "Nenhuma porta respondeu, mas IPP é a primeira opção recomendada.",
                        40,
                    ),
                    ProtocolRecommendation(
                        "JetDirect",
                        f"socket://{host}:9100",
                        "Tentar JetDirect",
                        "Alternativa comum para impressoras com IP fixo.",
                        30,
                    ),
                )
            )
        return sorted(recommendations, key=lambda item: item.confidence, reverse=True)

    @staticmethod
    def windows_share(server: str, share: str) -> ProtocolRecommendation:
        return ProtocolRecommendation(
            "SMB",
            f"smb://{server.strip()}/{share.strip()}",
            "Compartilhamento do Windows",
            "Use para impressora compartilhada por outro computador Windows.",
            100,
        )
