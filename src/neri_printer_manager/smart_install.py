"""Instalação inteligente com fallback de protocolo e driver.

O objetivo é evitar que o usuário precise conhecer PPD, IPP Everywhere ou
JetDirect. Cada tentativa é explícita, limitada e validada.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from .core import CupsService, PrinterManagerError, validate_device_uri, validate_queue_name
from .host_locator import LocatedPrinter


@dataclass(frozen=True, slots=True)
class InstallAttempt:
    uri: str
    model: str
    description: str


@dataclass(frozen=True, slots=True)
class InstallOutcome:
    queue: str
    uri: str
    model: str
    description: str
    attempts: int


class SmartPrinterInstaller:
    """Tenta combinações seguras até encontrar uma instalação compatível."""

    GENERIC_MODELS = (
        ("drv:///sample.drv/generic.ppd", "PostScript genérico"),
        ("drv:///sample.drv/generpcl.ppd", "PCL genérico"),
    )

    def __init__(self, cups: CupsService | None = None) -> None:
        self.cups = cups or CupsService()

    @staticmethod
    def _network_fallbacks(item: LocatedPrinter) -> list[str]:
        host = item.address
        uris: list[str] = [item.uri]
        if item.protocol == "IPP":
            uris.extend((f"socket://{host}:9100", f"lpd://{host}/lp"))
        elif item.protocol == "JetDirect":
            uris.append(f"lpd://{host}/lp")
        return list(dict.fromkeys(uris))

    def plan(self, item: LocatedPrinter) -> list[InstallAttempt]:
        if item.protocol == "SMB":
            return [
                InstallAttempt(item.uri, model, description)
                for model, description in self.GENERIC_MODELS
            ]

        attempts: list[InstallAttempt] = []
        for uri in self._network_fallbacks(item):
            scheme = urlparse(uri).scheme.lower()
            if scheme in {"ipp", "ipps"}:
                attempts.append(InstallAttempt(uri, "everywhere", "IPP sem driver"))
            attempts.extend(
                InstallAttempt(uri, model, description)
                for model, description in self.GENERIC_MODELS
            )
        return attempts

    def install(self, queue: str, item: LocatedPrinter) -> InstallOutcome:
        safe_queue = validate_queue_name(queue)
        failures: list[str] = []
        attempts = self.plan(item)
        for index, attempt in enumerate(attempts, start=1):
            try:
                self.cups.add_printer(
                    safe_queue,
                    validate_device_uri(attempt.uri),
                    attempt.model,
                )
                return InstallOutcome(
                    safe_queue,
                    attempt.uri,
                    attempt.model,
                    attempt.description,
                    index,
                )
            except PrinterManagerError as exc:
                failures.append(f"{attempt.description} em {attempt.uri}: {exc}")
                try:
                    self.cups.remove_printer(safe_queue)
                except PrinterManagerError:
                    pass

        detail = "\n".join(failures[-4:])
        raise PrinterManagerError(
            "Não foi possível instalar automaticamente. As opções compatíveis foram testadas."
            + (f"\n\nÚltimas tentativas:\n{detail}" if detail else "")
        )
