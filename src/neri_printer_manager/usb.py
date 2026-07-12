"""Detecção, instalação e compartilhamento seguro de impressoras USB."""
from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import unquote, urlparse

from .core import CommandRunner, CupsService, PrinterManagerError, validate_queue_name


@dataclass(frozen=True, slots=True)
class UsbPrinter:
    uri: str
    name: str
    manufacturer: str
    model: str
    driver: str
    driver_description: str


class UsbPrinterService:
    """Localiza dispositivos USB e escolhe o driver CUPS mais compatível."""

    FALLBACKS = (
        ("everywhere", "Driverless / IPP Everywhere"),
        ("drv:///sample.drv/generic.ppd", "PostScript genérico"),
        ("drv:///sample.drv/generpcl.ppd", "PCL genérico"),
    )

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=40)

    def detect(self) -> list[UsbPrinter]:
        result = self.runner.run(["lpinfo", "-v"], check=False)
        models = self._models()
        found: list[UsbPrinter] = []
        seen: set[str] = set()
        for line in result.stdout.splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) != 2 or not parts[1].lower().startswith("usb://"):
                continue
            uri = parts[1].strip()
            if uri in seen:
                continue
            seen.add(uri)
            manufacturer, model = self._identity(uri)
            driver, description = self._best_driver(manufacturer, model, models)
            name = " ".join(value for value in (manufacturer, model) if value).strip()
            found.append(UsbPrinter(uri, name or "Impressora USB", manufacturer, model, driver, description))
        return found

    def _models(self) -> list[tuple[str, str]]:
        result = self.runner.run(["lpinfo", "-m"], check=False)
        rows: list[tuple[str, str]] = []
        for line in result.stdout.splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                rows.append((parts[0], parts[1]))
        return rows

    @staticmethod
    def _identity(uri: str) -> tuple[str, str]:
        parsed = urlparse(uri)
        manufacturer = unquote(parsed.netloc).replace("_", " ").strip()
        model = unquote(parsed.path.strip("/")).replace("_", " ").strip()
        return manufacturer, model

    def _best_driver(self, manufacturer: str, model: str, rows: list[tuple[str, str]]) -> tuple[str, str]:
        tokens = [token.lower() for token in re.findall(r"[A-Za-z0-9]+", f"{manufacturer} {model}") if len(token) >= 2]
        best: tuple[int, str, str] | None = None
        for driver, description in rows:
            text = description.lower()
            score = sum(3 if token in text else 0 for token in tokens)
            if manufacturer and manufacturer.lower() in text:
                score += 8
            if model and model.lower() in text:
                score += 15
            if score and (best is None or score > best[0]):
                best = (score, driver, description)
        if best:
            return best[1], best[2]
        # USB normalmente não aceita "everywhere"; prefira drivers genéricos.
        return self.FALLBACKS[1]

    def install(self, printer: UsbPrinter, queue: str | None = None) -> str:
        safe = validate_queue_name(queue or re.sub(r"[^A-Za-z0-9_.-]+", "-", printer.name).strip("-") or "Impressora-USB")
        attempts = [(printer.driver, printer.driver_description), *self.FALLBACKS[1:]]
        errors: list[str] = []
        for driver, description in dict.fromkeys(attempts):
            try:
                CupsService(self.runner).add_printer(safe, printer.uri, driver)
                return f"{safe} — {description}"
            except PrinterManagerError as exc:
                errors.append(str(exc))
                try:
                    CupsService(self.runner).remove_printer(safe)
                except PrinterManagerError:
                    pass
        raise PrinterManagerError("Não foi possível instalar a impressora USB. " + " | ".join(errors[-2:]))

    def share(self, queue: str) -> str:
        safe = validate_queue_name(queue)
        helper = "/usr/libexec/neri-printer-helper"
        self.runner.run(["pkexec", helper, "enable-printer-sharing", safe])
        return f"A fila {safe} foi compartilhada pelo CUPS e pelo Samba."
