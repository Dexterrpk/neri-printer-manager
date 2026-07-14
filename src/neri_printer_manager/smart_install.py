"""Instalação inteligente com autenticação, driver compatível e validação da fila."""
from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse, urlunparse

from .core import CommandRunner, CupsService, PrinterManagerError, validate_device_uri, validate_queue_name
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
    test_page_submitted: bool = False


class DriverCatalog:
    """Consulta os drivers disponíveis no CUPS e ordena os mais compatíveis."""

    GENERIC_MODELS = (
        ("drv:///sample.drv/generic.ppd", "PostScript genérico"),
        ("drv:///sample.drv/generpcl.ppd", "PCL genérico"),
    )

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=40)

    def available(self) -> list[tuple[str, str]]:
        result = self.runner.run(["lpinfo", "-m"], check=False)
        rows: list[tuple[str, str]] = []
        for line in result.stdout.splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                rows.append((parts[0].strip(), parts[1].strip()))
        return rows

    @staticmethod
    def _tokens(text: str) -> list[str]:
        ignored = {"printer", "series", "class", "driver", "shared", "impressora", "fila"}
        return [
            token.lower()
            for token in re.findall(r"[A-Za-z0-9]+", text)
            if len(token) >= 2 and token.lower() not in ignored
        ]

    def ranked(self, identity: str, *, limit: int = 6) -> list[tuple[str, str]]:
        tokens = self._tokens(identity)
        if not tokens:
            return []
        scored: list[tuple[int, str, str]] = []
        identity_lower = identity.lower().strip()
        for model, description in self.available():
            haystack = f"{model} {description}".lower()
            score = 0
            for token in tokens:
                if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", haystack):
                    score += 8
                elif token in haystack:
                    score += 3
            if identity_lower and identity_lower in haystack:
                score += 40
            if any(tag in haystack for tag in ("hpcups", "hplip", "gutenprint", "foomatic")):
                score += 2
            if score > 0:
                scored.append((score, model, description))
        scored.sort(key=lambda row: (-row[0], row[2].lower()))
        return [(model, description) for _, model, description in scored[:limit]]


class SmartPrinterInstaller:
    """Tenta primeiro o PPD exato, valida a fila e usa genéricos só no fim."""

    GENERIC_MODELS = DriverCatalog.GENERIC_MODELS

    def __init__(
        self,
        cups: CupsService | None = None,
        runner: CommandRunner | None = None,
        catalog: DriverCatalog | None = None,
    ) -> None:
        self.cups = cups or CupsService(runner)
        self.runner = runner or getattr(self.cups, "runner", None) or CommandRunner(timeout=40)
        self.catalog = catalog or DriverCatalog(self.runner)

    @staticmethod
    def _network_fallbacks(item: LocatedPrinter) -> list[str]:
        host = item.address
        uris: list[str] = [item.uri]
        if item.protocol == "IPP":
            uris.extend((f"socket://{host}:9100", f"lpd://{host}/lp"))
        elif item.protocol == "JetDirect":
            uris.append(f"lpd://{host}/lp")
        return list(dict.fromkeys(uris))

    @staticmethod
    def _safe_display_uri(uri: str) -> str:
        parsed = urlparse(uri)
        if parsed.username is None:
            return uri
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunparse((parsed.scheme, host, parsed.path, parsed.params, parsed.query, parsed.fragment))

    def _driver_candidates(self, item: LocatedPrinter) -> list[tuple[str, str]]:
        identity = " ".join(
            part for part in (item.name, getattr(item, "model_hint", ""), item.host) if part
        )
        exact = self.catalog.ranked(identity)
        return list(dict.fromkeys([*exact, *self.GENERIC_MODELS]))

    def plan(self, item: LocatedPrinter) -> list[InstallAttempt]:
        drivers = self._driver_candidates(item)
        if item.protocol == "SMB":
            authenticated_uri = item.installation_uri()
            return [InstallAttempt(authenticated_uri, model, description) for model, description in drivers]

        attempts: list[InstallAttempt] = []
        for uri in self._network_fallbacks(item):
            scheme = urlparse(uri).scheme.lower()
            if scheme in {"ipp", "ipps"}:
                attempts.append(InstallAttempt(uri, "everywhere", "IPP Everywhere / driverless"))
            attempts.extend(InstallAttempt(uri, model, description) for model, description in drivers)
        return list(dict.fromkeys(attempts))

    def _validate_and_test(self, queue: str) -> bool:
        if hasattr(self.cups, "resume"):
            self.cups.resume(queue)
        if hasattr(self.cups, "verify_printer"):
            self.cups.verify_printer(queue)
        if hasattr(self.cups, "print_test_page"):
            self.cups.print_test_page(queue)
            return True
        return False

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
                tested = self._validate_and_test(safe_queue)
                return InstallOutcome(
                    safe_queue,
                    self._safe_display_uri(attempt.uri),
                    attempt.model,
                    attempt.description,
                    index,
                    tested,
                )
            except PrinterManagerError as exc:
                failures.append(
                    f"{attempt.description} em {self._safe_display_uri(attempt.uri)}: {exc}"
                )
                try:
                    self.cups.remove_printer(safe_queue)
                except PrinterManagerError:
                    pass

        detail = "\n".join(failures[-6:])
        raise PrinterManagerError(
            "A impressora foi localizada, mas nenhuma combinação de autenticação, protocolo e driver passou na validação."
            + (f"\n\nÚltimas tentativas:\n{detail}" if detail else "")
        )
