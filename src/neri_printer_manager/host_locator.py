"""Busca direcionada de impressoras por IP ou hostname.

O usuário informa apenas o endereço da impressora ou do computador remoto. O
serviço resolve o host, testa os protocolos conhecidos, consulta o CUPS e lista
compartilhamentos SMB quando disponíveis.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import socket

from .core import CommandRunner
from .network import NetworkService, PortState


@dataclass(frozen=True, slots=True)
class LocatedPrinter:
    name: str
    host: str
    address: str
    connection: str
    protocol: str
    uri: str
    recommended: bool
    explanation: str


class HostPrinterLocator:
    """Localiza opções de impressão para um host informado pelo usuário."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=15)

    @staticmethod
    def resolve(host: str) -> tuple[str, str]:
        safe_host = NetworkService.validate_host(host)
        address = socket.gethostbyname(safe_host)
        try:
            canonical = socket.gethostbyaddr(address)[0]
        except OSError:
            canonical = safe_host
        return canonical, address

    def locate(self, host: str) -> list[LocatedPrinter]:
        canonical, address = self.resolve(host)
        results: list[LocatedPrinter] = []
        checks = {item.port: item for item in NetworkService().scan_printer_ports(address)}

        if checks[631].state is PortState.OPEN:
            results.append(
                LocatedPrinter(
                    name=f"Impressora em {canonical}",
                    host=canonical,
                    address=address,
                    connection="Impressora de rede",
                    protocol="IPP",
                    uri=f"ipp://{address}/ipp/print",
                    recommended=True,
                    explanation="IPP é o método mais moderno e normalmente funciona sem driver específico.",
                )
            )

        if checks[9100].state is PortState.OPEN:
            results.append(
                LocatedPrinter(
                    name=f"Impressora em {canonical}",
                    host=canonical,
                    address=address,
                    connection="Impressora de rede",
                    protocol="JetDirect",
                    uri=f"socket://{address}:9100",
                    recommended=not results,
                    explanation="Conexão direta pela porta 9100; boa alternativa quando IPP não está disponível.",
                )
            )

        if checks[515].state is PortState.OPEN:
            results.append(
                LocatedPrinter(
                    name=f"Impressora em {canonical}",
                    host=canonical,
                    address=address,
                    connection="Impressora de rede",
                    protocol="LPD",
                    uri=f"lpd://{address}/lp",
                    recommended=not results,
                    explanation="Protocolo legado, usado apenas quando IPP e JetDirect não estão disponíveis.",
                )
            )

        if checks[445].state is PortState.OPEN or checks[139].state is PortState.OPEN:
            results.extend(self._smb_printers(canonical, address, recommended=not results))

        return results

    def _smb_printers(
        self,
        canonical: str,
        address: str,
        *,
        recommended: bool,
    ) -> list[LocatedPrinter]:
        if not self.runner.exists("smbclient"):
            return []
        response = self.runner.run(
            ["smbclient", "-N", "-g", "-L", f"//{address}"],
            check=False,
        )
        printers: list[LocatedPrinter] = []
        for line in response.stdout.splitlines():
            parts = line.split("|")
            if len(parts) < 2 or parts[0].strip().lower() != "printer":
                continue
            share = parts[1].strip()
            if not share or not re.fullmatch(r"[A-Za-z0-9$_. -]{1,127}", share):
                continue
            printers.append(
                LocatedPrinter(
                    name=share,
                    host=canonical,
                    address=address,
                    connection="Compartilhada por computador Windows/Linux",
                    protocol="SMB",
                    uri=f"smb://{address}/{share.replace(' ', '%20')}",
                    recommended=recommended and not printers,
                    explanation="Impressora compartilhada encontrada automaticamente no computador informado.",
                )
            )
        return printers
