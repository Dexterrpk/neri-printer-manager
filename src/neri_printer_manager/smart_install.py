"""Instalação inteligente com autenticação, driver compatível e validação da fila."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from .core import (
    CommandRunner,
    CupsService,
    PrinterManagerError,
    validate_device_uri,
    validate_queue_name,
)
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
        try:
            address = ipaddress.ip_address(item.address)
            host = f"[{address}]" if isinstance(address, ipaddress.IPv6Address) else str(address)
        except ValueError:
            host = item.address
        uris: list[str] = [item.uri]
        if item.protocol == "IPP":
            uris.extend((f"socket://{host}:9100", f"lpd://{host}/lp"))
        elif item.protocol == "JetDirect":
            uris.append(f"lpd://{host}/lp")
        return list(dict.fromkeys(uris))

    def _ensure_queue_available(self, queue: str) -> None:
        queue_exists = getattr(self.cups, "queue_exists", None)
        if callable(queue_exists) and queue_exists(queue):
            raise PrinterManagerError(
                f"Já existe uma fila chamada '{queue}'. Escolha outro nome para não "
                "alterar uma impressora que já funciona."
            )

    @staticmethod
    def _safe_display_uri(uri: str) -> str:
        try:
            parsed = urlparse(uri)
            if parsed.username is None:
                return uri
            host = parsed.hostname or ""
            if ":" in host:
                host = f"[{host}]"
            if parsed.port:
                host = f"{host}:{parsed.port}"
            return urlunparse(
                (parsed.scheme, host, parsed.path, parsed.params, parsed.query, parsed.fragment)
            )
        except ValueError:
            return "URI inválida"

    def _driver_candidates(self, item: LocatedPrinter) -> list[tuple[str, str]]:
        identity = " ".join(
            part for part in (item.name, getattr(item, "model_hint", ""), item.host) if part
        )
        exact = self.catalog.ranked(identity)
        return list(dict.fromkeys([*exact, *self.GENERIC_MODELS]))

    def plan(self, item: LocatedPrinter) -> list[InstallAttempt]:
        drivers = self._driver_candidates(item)
        if item.protocol == "SMB":
            return [InstallAttempt(item.uri, model, description) for model, description in drivers]

        attempts: list[InstallAttempt] = []
        for uri in self._network_fallbacks(item):
            scheme = urlparse(uri).scheme.lower()
            if scheme in {"ipp", "ipps"}:
                attempts.append(InstallAttempt(uri, "everywhere", "IPP Everywhere / driverless"))
            attempts.extend(
                InstallAttempt(uri, model, description) for model, description in drivers
            )
        return list(dict.fromkeys(attempts))

    def _validate_and_test(self, queue: str) -> bool:
        if hasattr(self.cups, "verify_printer"):
            self.cups.verify_printer(queue)
        if hasattr(self.cups, "print_test_page"):
            try:
                self.cups.print_test_page(queue)
                return True
            except PrinterManagerError:
                return False
        return False

    def install(self, queue: str, item: LocatedPrinter) -> InstallOutcome:
        safe_queue = validate_queue_name(queue)
        self._ensure_queue_available(safe_queue)
        failures: list[str] = []
        attempts = self.plan(item)
        for index, attempt in enumerate(attempts, start=1):
            created = False
            try:
                safe_uri = validate_device_uri(attempt.uri)
                if item.protocol == "SMB" and item.username:
                    add_authenticated = getattr(self.cups, "add_authenticated_printer", None)
                    if not callable(add_authenticated):
                        raise PrinterManagerError(
                            "O serviço CUPS não oferece o fluxo seguro de autenticação SMB."
                        )
                    add_authenticated(
                        safe_queue,
                        safe_uri,
                        attempt.model,
                        item.username,
                        item.password,
                    )
                else:
                    self.cups.add_printer(safe_queue, safe_uri, attempt.model)
                created = True
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
                if created:
                    try:
                        self.cups.remove_printer(safe_queue)
                    except PrinterManagerError:
                        failures.append(
                            "A tentativa criou uma fila incompleta que não pôde ser removida."
                        )
                        break

        detail = "\n".join(failures[-6:])
        raise PrinterManagerError(
            "A impressora foi localizada, mas nenhuma combinação de autenticação, protocolo e driver passou na validação."
            + (f"\n\nÚltimas tentativas:\n{detail}" if detail else "")
        )
