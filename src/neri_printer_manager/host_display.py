"""Resolve nomes amigáveis para equipamentos descobertos por endereço IP."""
from __future__ import annotations

import ipaddress
import re
import socket

from .core import CommandRunner


class HostDisplayResolver:
    """Tenta DNS reverso e NetBIOS sem repetir o próprio IP como hostname."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=5)
        self._cache: dict[str, str] = {}

    @staticmethod
    def _is_ip(value: str) -> bool:
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False

    @staticmethod
    def _clean(value: str) -> str:
        text = re.sub(r"[\x00-\x1f\x7f]+", " ", value or "")
        text = re.sub(r"\s+", " ", text).strip().rstrip(".")
        return text[:127]

    def resolve(self, host: str, address: str) -> str:
        host = self._clean(host)
        address = self._clean(address)

        if host and not self._is_ip(host) and host.lower() not in {
            "host não informado",
            "origem não identificada",
            "este computador",
        }:
            return host

        if not address or not self._is_ip(address):
            return "Este computador" if host.lower() == "este computador" else "Não identificado"

        if address in self._cache:
            return self._cache[address]

        resolved = self._reverse_dns(address) or self._netbios(address) or "Não identificado"
        self._cache[address] = resolved
        return resolved

    @staticmethod
    def _reverse_dns(address: str) -> str:
        try:
            name = socket.gethostbyaddr(address)[0].rstrip(".")
        except OSError:
            return ""
        return "" if HostDisplayResolver._is_ip(name) else HostDisplayResolver._clean(name)

    def _netbios(self, address: str) -> str:
        if not self.runner.exists("nmblookup"):
            return ""
        result = self.runner.run(["nmblookup", "-A", address], check=False)
        for line in result.stdout.splitlines():
            match = re.match(r"^\s*([^\s<]{1,63})\s+<00>\s+-\s+<ACTIVE>", line, re.IGNORECASE)
            if match:
                name = self._clean(match.group(1))
                if name and not name.startswith("__MSBROWSE__"):
                    return name
        return ""
