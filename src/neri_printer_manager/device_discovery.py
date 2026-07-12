"""Descoberta enriquecida de impressoras locais, de rede e publicadas.

Combina filas já instaladas no CUPS, backends do ``lpinfo`` e anúncios DNS-SD
obtidos pelo Avahi. O resultado informa o melhor nome conhecido, host/IP e onde
a impressora está instalada ou publicada.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import re
import socket
from urllib.parse import unquote, urlparse

from .core import CommandRunner, CupsService


@dataclass(frozen=True, slots=True)
class DiscoveredPrinter:
    name: str
    model: str
    host: str
    address: str
    protocol: str
    uri: str
    location: str
    installed_queue: str = ""


class RichDiscoveryService:
    """Descobre impressoras sem confundir anúncio remoto com fila instalada."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=25)

    def discover(self) -> list[DiscoveredPrinter]:
        installed = CupsService(self.runner).list_printers()
        by_uri: dict[str, DiscoveredPrinter] = {}
        queue_by_uri = {item.device_uri: item.name for item in installed if item.device_uri}

        for printer in installed:
            uri = printer.device_uri or ""
            host, address = self._host_address(uri)
            by_uri[uri or f"queue:{printer.name}"] = DiscoveredPrinter(
                name=printer.name,
                model=self._friendly_name(uri) or printer.name,
                host=host,
                address=address,
                protocol=self._protocol(uri),
                uri=uri,
                location=f"Instalada neste computador como fila '{printer.name}'",
                installed_queue=printer.name,
            )

        if self.runner.exists("lpinfo"):
            result = self.runner.run(["lpinfo", "-v"], check=False)
            for line in result.stdout.splitlines():
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    continue
                backend, uri = parts
                if uri in by_uri:
                    continue
                host, address = self._host_address(uri)
                queue = queue_by_uri.get(uri, "")
                by_uri[uri] = DiscoveredPrinter(
                    name=self._friendly_name(uri) or host or "Impressora detectada",
                    model=self._friendly_name(uri) or "Modelo não informado",
                    host=host,
                    address=address,
                    protocol=self._protocol(uri, backend),
                    uri=uri,
                    location=(
                        f"Instalada neste computador como fila '{queue}'"
                        if queue
                        else self._remote_location(host, address)
                    ),
                    installed_queue=queue,
                )

        for item in self._avahi_printers():
            current = by_uri.get(item.uri)
            if current:
                by_uri[item.uri] = replace(
                    current,
                    name=item.name or current.name,
                    model=item.model if item.model != "Modelo não informado" else current.model,
                    host=item.host or current.host,
                    address=item.address or current.address,
                    location=current.location if current.installed_queue else item.location,
                )
            else:
                by_uri[item.uri] = item

        return sorted(
            by_uri.values(),
            key=lambda item: (not bool(item.installed_queue), item.name.lower(), item.host.lower()),
        )

    def _avahi_printers(self) -> list[DiscoveredPrinter]:
        if not self.runner.exists("avahi-browse"):
            return []
        result = self.runner.run(
            ["avahi-browse", "-rtkp", "_ipp._tcp", "_ipps._tcp", "_printer._tcp"],
            check=False,
        )
        printers: list[DiscoveredPrinter] = []
        for raw in result.stdout.splitlines():
            if not raw.startswith("="):
                continue
            fields = raw.split(";")
            if len(fields) < 9:
                continue
            service_name = unquote(fields[3])
            service_type = fields[4]
            host = fields[6].rstrip(".")
            address = fields[7]
            port = fields[8]
            txt = ";".join(fields[9:])
            attrs = self._txt_attributes(txt)
            model = attrs.get("ty") or attrs.get("product", "").strip("()") or service_name
            note = attrs.get("note") or attrs.get("location") or ""
            resource = attrs.get("rp") or "ipp/print"
            scheme = "ipps" if service_type == "_ipps._tcp" else "ipp"
            if service_type == "_printer._tcp":
                scheme, resource = "lpd", attrs.get("rp") or "lp"
            uri = f"{scheme}://{address}:{port}/{resource.lstrip('/')}"
            printers.append(
                DiscoveredPrinter(
                    name=service_name,
                    model=model or "Modelo não informado",
                    host=host,
                    address=address,
                    protocol=scheme.upper(),
                    uri=uri,
                    location=(f"{note} — publicado por {host}" if note else f"Publicado por {host} ({address})"),
                )
            )
        return printers

    @staticmethod
    def _txt_attributes(text: str) -> dict[str, str]:
        attrs: dict[str, str] = {}
        for key, value in re.findall(r'"?([A-Za-z0-9_-]+)=([^";]*)"?', text):
            attrs[key.lower()] = unquote(value).strip()
        return attrs

    @staticmethod
    def _protocol(uri: str, fallback: str = "") -> str:
        scheme = urlparse(uri).scheme.upper()
        return scheme or fallback.upper() or "DESCONHECIDO"

    @staticmethod
    def _friendly_name(uri: str) -> str:
        parsed = urlparse(uri)
        if parsed.scheme == "usb":
            return unquote((parsed.netloc + parsed.path).strip("/")).replace("_", " ")
        path = unquote(parsed.path.strip("/"))
        if path and path.lower() not in {"ipp/print", "ipp/printer", "lp", "printers"}:
            return path.rsplit("/", 1)[-1].replace("_", " ")
        return ""

    @staticmethod
    def _host_address(uri: str) -> tuple[str, str]:
        parsed = urlparse(uri)
        host = parsed.hostname or ""
        if not host:
            return ("Este computador" if parsed.scheme == "usb" else "", "")
        try:
            address = socket.gethostbyname(host)
        except OSError:
            address = host if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host) else ""
        return host, address

    @staticmethod
    def _remote_location(host: str, address: str) -> str:
        if host and address and host != address:
            return f"Disponível em {host} ({address}); ainda não instalada localmente"
        if host:
            return f"Disponível em {host}; ainda não instalada localmente"
        return "Detectada pelo CUPS; origem não identificada"
