"""Diagnóstico de rede para protocolos de impressão."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import ipaddress
import socket


class PortState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class PortCheck:
    host: str
    port: int
    service: str
    state: PortState
    message: str


PRINTER_PORTS = {
    631: "IPP/CUPS",
    9100: "JetDirect/AppSocket",
    515: "LPD",
    445: "SMB",
    139: "NetBIOS/SMB",
}


class NetworkService:
    @staticmethod
    def validate_host(host: str) -> str:
        value = host.strip()
        if not value or len(value) > 253:
            raise ValueError("Host inválido")
        try:
            ipaddress.ip_address(value)
            return value
        except ValueError:
            labels = value.rstrip(".").split(".")
            if any(not label or len(label) > 63 for label in labels):
                raise ValueError("Host inválido")
            allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")
            if any(any(char not in allowed for char in label) for label in labels):
                raise ValueError("Host inválido")
            return value

    def check_port(self, host: str, port: int, timeout: float = 2.0) -> PortCheck:
        safe_host = self.validate_host(host)
        if port not in PRINTER_PORTS:
            return PortCheck(safe_host, port, "Desconhecido", PortState.INVALID, "Porta não autorizada")
        try:
            with socket.create_connection((safe_host, port), timeout=timeout):
                return PortCheck(safe_host, port, PRINTER_PORTS[port], PortState.OPEN, "Respondendo")
        except OSError as exc:
            return PortCheck(safe_host, port, PRINTER_PORTS[port], PortState.CLOSED, str(exc))

    def scan_printer_ports(self, host: str) -> list[PortCheck]:
        return [self.check_port(host, port) for port in PRINTER_PORTS]
