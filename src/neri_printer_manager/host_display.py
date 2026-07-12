"""Resolve nomes amigáveis para equipamentos descobertos por endereço IP.

A resolução é complementar: falhas de DNS/NetBIOS nunca podem interromper a
listagem de impressoras. Consultas NetBIOS usam timeout curto, cache e execução
concorrente para não bloquear a interface em redes com muitos dispositivos.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import ipaddress
import re
import socket
from typing import Iterable

from .core import CommandRunner, PrinterManagerError


class HostDisplayResolver:
    """Tenta DNS reverso e NetBIOS sem repetir o próprio IP como hostname."""

    UNKNOWN_HOSTS = {
        "host não informado",
        "origem não identificada",
        "este computador",
        "não identificado",
    }

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=1)
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

        if host and not self._is_ip(host) and host.lower() not in self.UNKNOWN_HOSTS:
            return host
        if host.lower() == "este computador":
            return "Este computador"
        if not address or not self._is_ip(address):
            return "Não identificado"
        if address in self._cache:
            return self._cache[address]

        resolved = self._reverse_dns(address) or self._netbios(address) or "Não identificado"
        self._cache[address] = resolved
        return resolved

    def resolve_many(self, pairs: Iterable[tuple[str, str]]) -> list[str]:
        values = list(pairs)
        if not values:
            return []
        # Limita concorrência para não gerar tempestade NetBIOS na rede.
        with ThreadPoolExecutor(max_workers=min(12, len(values))) as pool:
            return list(pool.map(lambda pair: self.resolve(*pair), values))

    @staticmethod
    def _reverse_dns(address: str) -> str:
        try:
            name = socket.gethostbyaddr(address)[0].rstrip(".")
        except (OSError, UnicodeError):
            return ""
        return "" if HostDisplayResolver._is_ip(name) else HostDisplayResolver._clean(name)

    def _netbios(self, address: str) -> str:
        if not self.runner.exists("nmblookup"):
            return ""
        try:
            result = self.runner.run(["nmblookup", "-A", address], check=False)
        except PrinterManagerError:
            # Timeout, host silencioso e firewall são condições normais de descoberta.
            return ""
        for line in result.stdout.splitlines():
            match = re.match(r"^\s*([^\s<]{1,63})\s+<00>\s+-\s+<ACTIVE>", line, re.IGNORECASE)
            if match:
                name = self._clean(match.group(1))
                if name and not name.startswith("__MSBROWSE__"):
                    return name
        return ""
