"""Detecção, instalação e compartilhamento seguro de impressoras USB."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from .core import (
    CommandRunner,
    CupsService,
    PrinterManagerError,
    validate_device_uri,
    validate_queue_name,
)
from .sharing import SharingService


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
        self.cups = CupsService(self.runner)

    def detect(self) -> list[UsbPrinter]:
        result = self.runner.run(["lpinfo", "-v"], check=False)
        models = self._models()
        found: list[UsbPrinter] = []
        seen: set[str] = set()
        for line in result.stdout.splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) != 2 or not parts[1].lower().startswith(("usb://", "hp:/usb/")):
                continue
            try:
                uri = validate_device_uri(parts[1].strip())
            except PrinterManagerError:
                continue
            if uri in seen:
                continue
            seen.add(uri)
            manufacturer, model = self._identity(uri)
            driver, description = self._best_driver(manufacturer, model, models)
            name = " ".join(value for value in (manufacturer, model) if value).strip()
            found.append(
                UsbPrinter(uri, name or "Impressora USB", manufacturer, model, driver, description)
            )
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
        if parsed.scheme.lower() == "hp":
            model = unquote(parsed.path.removeprefix("/usb/")).replace("_", " ").strip()
            return "HP", model
        manufacturer = unquote(parsed.netloc).replace("_", " ").strip()
        model = unquote(parsed.path.strip("/")).replace("_", " ").strip()
        return manufacturer, model

    def _best_driver(
        self, manufacturer: str, model: str, rows: list[tuple[str, str]]
    ) -> tuple[str, str]:
        tokens = [
            token.lower()
            for token in re.findall(r"[A-Za-z0-9]+", f"{manufacturer} {model}")
            if len(token) >= 2
        ]
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
        suggested = re.sub(r"[^A-Za-z0-9_.-]+", "-", printer.name).strip("-_.")[:80]
        safe = validate_queue_name(queue or suggested or "Impressora-USB")
        if self.cups.queue_exists(safe):
            raise PrinterManagerError(f"Já existe uma fila chamada '{safe}'. Escolha outro nome.")
        attempts = [(printer.driver, printer.driver_description), *self.FALLBACKS[1:]]
        errors: list[str] = []
        for driver, description in dict.fromkeys(attempts):
            created = False
            try:
                self.cups.add_printer(safe, printer.uri, driver)
                created = True
                self.cups.verify_printer(safe)
                try:
                    self.cups.print_test_page(safe)
                    test_status = "página de teste enviada"
                except PrinterManagerError:
                    test_status = "fila instalada; a página de teste não foi enviada"
                return f"{safe} — {description} — {test_status}"
            except PrinterManagerError as exc:
                errors.append(str(exc))
                if created:
                    try:
                        self.cups.remove_printer(safe)
                    except PrinterManagerError:
                        errors.append("A fila incompleta não pôde ser removida.")
                        break
        raise PrinterManagerError(
            "Não foi possível instalar a impressora USB. " + " | ".join(errors[-2:])
        )

    def share(self, queue: str) -> str:
        return SharingService(self.runner).enable_queue(queue)
