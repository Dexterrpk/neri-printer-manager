"""Busca de impressoras por IP/hostname com DNS, mDNS, NetBIOS e SMB."""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlparse

from .core import CommandRunner, PrinterManagerError, validate_queue_name
from .network import NetworkService, PortState
from .security import contains_control_characters


@dataclass(frozen=True, slots=True)
class ResolvedHost:
    requested: str
    canonical: str
    address: str
    method: str


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
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)


class HostPrinterLocator:
    """Localiza opções de impressão para um IP ou nome de máquina."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=15)

    @staticmethod
    def normalize_host(value: str) -> str:
        text = value.strip()
        if text.lower().startswith("smb://"):
            try:
                text = urlparse(text).hostname or ""
            except ValueError as exc:
                raise PrinterManagerError("O endereço SMB informado é inválido.") from exc
        text = text.lstrip("\\/").split("/", 1)[0].split("\\", 1)[0].strip()
        if not text:
            raise PrinterManagerError("Informe o IP ou nome do computador.")
        try:
            return NetworkService.validate_host(text)
        except ValueError as exc:
            raise PrinterManagerError("O IP ou nome do computador é inválido.") from exc

    @staticmethod
    def _credential(value: str, label: str, *, limit: int = 256) -> str:
        if len(value) > limit or contains_control_characters(value):
            raise PrinterManagerError(f"{label} contém caracteres inválidos.")
        return value

    @staticmethod
    def _uri_host(address: str) -> str:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return address
        return f"[{parsed}]" if isinstance(parsed, ipaddress.IPv6Address) else str(parsed)

    def resolve(self, host: str) -> ResolvedHost:
        requested = self.normalize_host(host)
        try:
            address = str(ipaddress.ip_address(requested))
            return ResolvedHost(
                requested,
                self._reverse_name(address),
                address,
                "IP informado",
            )
        except ValueError:
            pass
        for resolver in (
            self._resolve_dns,
            self._resolve_getent,
            self._resolve_mdns,
            self._resolve_netbios,
        ):
            resolved = resolver(requested)
            if resolved:
                return resolved
        raise PrinterManagerError(
            f"Não foi possível localizar '{requested}'. Verifique se a máquina está ligada, "
            "na mesma rede e se o nome está correto. Também pode tentar o endereço IP."
        )

    def _resolve_dns(self, host: str) -> ResolvedHost | None:
        candidates = [host]
        if "." not in host:
            candidates.append(f"{host}.local")
        for candidate in candidates:
            try:
                infos = socket.getaddrinfo(candidate, None, socket.AF_INET, socket.SOCK_STREAM)
            except socket.gaierror:
                continue
            addresses = sorted({str(item[4][0]) for item in infos})
            if addresses:
                address = addresses[0]
                return ResolvedHost(
                    host, self._reverse_name(address, candidate), address, "DNS/mDNS"
                )
        return None

    def _resolve_getent(self, host: str) -> ResolvedHost | None:
        if not self.runner.exists("getent"):
            return None
        for candidate in (host, f"{host}.local" if "." not in host else host):
            result = self.runner.run(["getent", "ahostsv4", candidate], check=False)
            for line in result.stdout.splitlines():
                address = line.split(maxsplit=1)[0] if line.strip() else ""
                if self._is_ipv4(address):
                    return ResolvedHost(
                        host, self._reverse_name(address, candidate), address, "getent"
                    )
        return None

    def _resolve_mdns(self, host: str) -> ResolvedHost | None:
        if not self.runner.exists("avahi-resolve-host-name"):
            return None
        candidate = host if host.endswith(".local") else f"{host}.local"
        result = self.runner.run(["avahi-resolve-host-name", "-4", candidate], check=False)
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and self._is_ipv4(parts[-1]):
                return ResolvedHost(host, parts[0].rstrip("."), parts[-1], "Avahi/mDNS")
        return None

    def _resolve_netbios(self, host: str) -> ResolvedHost | None:
        if not self.runner.exists("nmblookup"):
            return None
        result = self.runner.run(["nmblookup", host], check=False)
        for line in result.stdout.splitlines():
            match = re.match(r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+", line)
            if match and self._is_ipv4(match.group(1)):
                return ResolvedHost(host, host.upper(), match.group(1), "NetBIOS")
        return None

    @staticmethod
    def _is_ipv4(value: str) -> bool:
        try:
            return isinstance(ipaddress.ip_address(value), ipaddress.IPv4Address)
        except ValueError:
            return False

    @staticmethod
    def _reverse_name(address: str, fallback: str | None = None) -> str:
        try:
            return socket.gethostbyaddr(address)[0]
        except OSError:
            return fallback or address

    def locate(self, host: str, username: str = "", password: str = "") -> list[LocatedPrinter]:
        username = self._credential(username.strip(), "Usuário")
        password = self._credential(password, "Senha")
        if password and not username:
            raise PrinterManagerError("Informe também o usuário do computador remoto.")
        resolved = self.resolve(host)
        results: list[LocatedPrinter] = []
        checks = {item.port: item for item in NetworkService().scan_printer_ports(resolved.address)}
        uri_host = self._uri_host(resolved.address)

        if checks[631].state is PortState.OPEN:
            shared_queues = self._cups_shared_printers(resolved)
            if shared_queues:
                results.extend(shared_queues)
            else:
                results.append(
                    LocatedPrinter(
                        f"Impressora em {resolved.canonical}",
                        resolved.canonical,
                        resolved.address,
                        f"Impressora de rede — localizada por {resolved.method}",
                        "IPP",
                        f"ipp://{uri_host}/ipp/print",
                        True,
                        "IPP foi encontrado. O instalador testará driverless e "
                        "alternativas automaticamente.",
                    )
                )
        if checks[9100].state is PortState.OPEN:
            results.append(
                LocatedPrinter(
                    f"Impressora em {resolved.canonical}",
                    resolved.canonical,
                    resolved.address,
                    f"Impressora de rede — localizada por {resolved.method}",
                    "JetDirect",
                    f"socket://{uri_host}:9100",
                    not results,
                    "Conexão direta pela porta 9100, comum em impressoras corporativas.",
                )
            )
        if checks[515].state is PortState.OPEN:
            results.append(
                LocatedPrinter(
                    f"Impressora em {resolved.canonical}",
                    resolved.canonical,
                    resolved.address,
                    f"Impressora de rede — localizada por {resolved.method}",
                    "LPD",
                    f"lpd://{uri_host}/lp",
                    not results,
                    "Protocolo legado usado quando IPP e JetDirect não estão disponíveis.",
                )
            )

        smb_available = any(checks[port].state is PortState.OPEN for port in (445, 139))
        smb_results: list[LocatedPrinter] = []
        if smb_available:
            try:
                smb_results = self._smb_printers(
                    resolved,
                    username,
                    password,
                    recommended=not results,
                )
            except PrinterManagerError:
                # A ausência do cliente SMB não deve esconder uma opção IPP,
                # JetDirect ou LPD que já foi confirmada no mesmo equipamento.
                if not results:
                    raise
        existing_uris = {item.uri for item in results}
        results.extend(item for item in smb_results if item.uri not in existing_uris)

        if not results:
            credential_hint = (
                "As credenciais informadas não deram acesso às filas compartilhadas."
                if username
                else "O acesso anônimo não mostrou filas. Informe usuário e senha do computador remoto."
            )
            raise PrinterManagerError(
                f"O computador {resolved.canonical} foi localizado em {resolved.address} por "
                f"{resolved.method}, mas não publicou nenhuma impressora acessível. {credential_hint}"
            )
        return results

    def _cups_shared_printers(self, resolved: ResolvedHost) -> list[LocatedPrinter]:
        """Enumera filas de outro Mint/CUPS em vez de inventar ``/ipp/print``."""

        if not self.runner.exists("lpstat"):
            return []
        server = f"{self._uri_host(resolved.address)}:631"
        response = self.runner.run(["lpstat", "-h", server, "-e"], check=False)
        queues: list[LocatedPrinter] = []
        for raw in response.stdout.splitlines():
            queue = raw.strip().split(maxsplit=1)[0] if raw.strip() else ""
            try:
                safe_queue = validate_queue_name(queue)
            except PrinterManagerError:
                continue
            queues.append(
                LocatedPrinter(
                    safe_queue,
                    resolved.canonical,
                    resolved.address,
                    f"Compartilhada por outro Linux Mint — localizada por {resolved.method}",
                    "IPP",
                    f"ipp://{self._uri_host(resolved.address)}:631/printers/"
                    f"{quote(safe_queue, safe='')}",
                    not queues,
                    "Fila publicada pelo CUPS remoto. Esta é a opção correta para "
                    "compartilhamento Mint para Mint.",
                )
            )
        return queues

    def _smb_printers(
        self,
        resolved: ResolvedHost,
        username: str,
        password: str,
        *,
        recommended: bool,
    ) -> list[LocatedPrinter]:
        if not self.runner.exists("smbclient"):
            raise PrinterManagerError(
                "O computador oferece compartilhamento Windows, mas o componente "
                "smbclient não está instalado. Use a Central de saúde para instalar "
                "o suporte SMB."
            )
        targets = list(
            dict.fromkeys(filter(None, (resolved.requested, resolved.canonical, resolved.address)))
        )
        outputs: list[str] = []

        auth_path: Path | None = None
        try:
            if username:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
                    auth_path = Path(handle.name)
                    handle.write(f"username = {username}\npassword = {password}\n")
                os.chmod(auth_path, 0o600)

            for target in targets:
                command = ["smbclient", "-g", "-L", f"//{target}"]
                if auth_path:
                    command[1:1] = ["-A", str(auth_path)]
                else:
                    command[1:1] = ["-N"]
                response = self.runner.run(command, check=False)
                if response.stdout:
                    outputs.append(response.stdout)
        finally:
            if auth_path:
                auth_path.unlink(missing_ok=True)

        printers: list[LocatedPrinter] = []
        seen: set[str] = set()
        for output in outputs:
            for line in output.splitlines():
                parts = line.split("|")
                if len(parts) < 2 or parts[0].strip().lower() != "printer":
                    continue
                share = parts[1].strip()
                share_key = share.casefold()
                if (
                    not share
                    or share_key in seen
                    or len(share) > 127
                    or contains_control_characters(share)
                    or any(character in "/\\" for character in share)
                ):
                    continue
                seen.add(share_key)
                printers.append(
                    LocatedPrinter(
                        share,
                        resolved.canonical,
                        resolved.address,
                        f"Compartilhada por computador — localizado por {resolved.method}",
                        "SMB",
                        f"smb://{self._uri_host(resolved.address)}/{quote(share, safe='$_.-')}",
                        recommended and not printers,
                        "Impressora compartilhada encontrada com acesso autenticado."
                        if username
                        else "Impressora compartilhada encontrada sem autenticação.",
                        username,
                        password,
                    )
                )
        return printers
