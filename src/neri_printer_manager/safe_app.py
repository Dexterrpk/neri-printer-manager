"""Inicialização segura da interface com descoberta tolerante a nomes DNS-SD inválidos."""
from __future__ import annotations

import ipaddress
import re
import socket
import sys
from urllib.parse import urlparse

from PySide6.QtWidgets import QApplication

from .device_discovery import RichDiscoveryService
from .enhanced_app import EnhancedWindow
from .logging_config import configure_logging


class SafeRichDiscoveryService(RichDiscoveryService):
    """Ignora nomes que não podem ser convertidos pelo codec IDNA do sistema."""

    @staticmethod
    def _valid_dns_host(host: str) -> bool:
        if not host or len(host) > 253 or " " in host:
            return False
        labels = host.rstrip(".").split(".")
        if any(not label or len(label.encode("utf-8", errors="ignore")) > 63 for label in labels):
            return False
        try:
            host.encode("idna")
        except UnicodeError:
            return False
        return True

    @classmethod
    def _host_address(cls, uri: str) -> tuple[str, str]:
        try:
            parsed = urlparse(uri)
            host = parsed.hostname or ""
        except (ValueError, UnicodeError):
            return "", ""

        if not host:
            return ("Este computador" if uri.lower().startswith("usb:") else "", "")

        try:
            ipaddress.ip_address(host)
            return host, host
        except ValueError:
            pass

        # dnssd:// normalmente contém um nome de serviço, não um hostname DNS.
        # Ele deve ser exibido, mas nunca enviado diretamente ao resolvedor.
        if parsed.scheme.lower() == "dnssd" or not cls._valid_dns_host(host):
            return host[:240], ""

        try:
            return host, socket.gethostbyname(host)
        except (OSError, UnicodeError, ValueError):
            return host[:240], ""


class SafeEnhancedWindow(EnhancedWindow):
    def discover_devices(self) -> None:
        self.tools_status.setText(
            "Consultando filas locais, CUPS, IPP, Avahi e a rede local..."
        )
        self._run(SafeRichDiscoveryService().discover, self._show_discovered)


def main() -> int:
    configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Neri Printer Manager")
    window = SafeEnhancedWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
