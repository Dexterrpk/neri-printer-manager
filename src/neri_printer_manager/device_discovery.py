"""Descoberta enriquecida de impressoras locais, de rede e publicadas.

A implementação evita depender de uma única ferramenta e nunca transforma falhas
parciais de Avahi/CUPS em fechamento da interface. Filas locais têm prioridade e
anúncios de rede apenas complementam nome, modelo, host e localização.
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

    SERVICE_TYPES = ("_ipp._tcp", "_ipps._tcp", "_printer._tcp")

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=25)

    @staticmethod
    def _safe_text(value: object, fallback: str, limit: int = 240) -> str:
        text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or ""))
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            text = fallback
        return text[:limit]

    def discover(self) -> list[DiscoveredPrinter]:
        installed = CupsService(self.runner).list_printers()
        by_uri: dict[str, DiscoveredPrinter] = {}
        queue_by_uri = {item.device_uri: item.name for item in installed if item.device_uri}

        for printer in installed:
            uri = printer.device_uri or ""
            host, address = self._host_address(uri)
            name = self._safe_text(printer.name, "Fila instalada", 127)
            by_uri[uri or f"queue:{name}"] = DiscoveredPrinter(
                name=name,
                model=self._safe_text(self._friendly_name(uri), name),
                host=self._safe_text(host, "Este computador"),
                address=self._safe_text(address, "Local"),
                protocol=self._safe_text(self._protocol(uri), "LOCAL", 32),
                uri=uri,
                location=f"Instalada neste computador como fila '{name}'",
                installed_queue=name,
            )

        if self.runner.exists("lpinfo"):
            result = self.runner.run(["lpinfo", "-v"], check=False)
            for line in result.stdout.splitlines():
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    continue
                backend, uri = parts[0].strip(), parts[1].strip()
                if not uri or len(uri) > 2048 or uri in by_uri:
                    continue
                host, address = self._host_address(uri)
                queue = queue_by_uri.get(uri, "")
                friendly = self._safe_text(self._friendly_name(uri), host or "Impressora detectada")
                by_uri[uri] = DiscoveredPrinter(
                    name=friendly,
                    model=friendly,
                    host=self._safe_text(host, "Origem não identificada"),
                    address=self._safe_text(address, "Não informado"),
                    protocol=self._safe_text(self._protocol(uri, backend), "DESCONHECIDO", 32),
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
        printers: list[DiscoveredPrinter] = []
        seen: set[str] = set()
        # Avahi aceita um tipo por chamada. Passar vários tipos pode gerar
        # "label empty or too long" em algumas versões.
        for service_type in self.SERVICE_TYPES:
            result = self.runner.run(
                ["avahi-browse", "--resolve", "--terminate", "--parsable", service_type],
                check=False,
            )
            if result.returncode != 0:
                continue
            for raw in result.stdout.splitlines():
                item = self._parse_avahi_line(raw)
                if item and item.uri not in seen:
                    seen.add(item.uri)
                    printers.append(item)
        return printers

    def _parse_avahi_line(self, raw: str) -> DiscoveredPrinter | None:
        if not raw.startswith("="):
            return None
        fields = raw.split(";")
        if len(fields) < 9:
            return None
        service_name = self._safe_text(unquote(fields[3]), "Impressora anunciada")
        service_type = fields[4].strip()
        host = self._safe_text(fields[6].rstrip("."), "Host não informado")
        address = self._safe_text(fields[7], "IP não informado", 64)
        port = fields[8].strip()
        if not port.isdigit():
            return None
        attrs = self._txt_attributes(";".join(fields[9:]))
        model = self._safe_text(
            attrs.get("ty") or attrs.get("product", "").strip("()") or service_name,
            "Modelo não informado",
        )
        note = self._safe_text(attrs.get("note") or attrs.get("location"), "", 180)
        resource = self._safe_text(attrs.get("rp"), "ipp/print", 180).lstrip("/")
        scheme = "ipps" if service_type == "_ipps._tcp" else "ipp"
        if service_type == "_printer._tcp":
            scheme = "lpd"
            resource = self._safe_text(attrs.get("rp"), "lp", 180).lstrip("/")
        uri = f"{scheme}://{address}:{port}/{resource}"
        location = f"{note} — publicado por {host}" if note else f"Publicado por {host} ({address})"
        return DiscoveredPrinter(
            name=service_name,
            model=model,
            host=host,
            address=address,
            protocol=scheme.upper(),
            uri=uri,
            location=location,
        )

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
