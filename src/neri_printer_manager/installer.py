"""Instalação inteligente de filas com fallback seguro.

Algumas impressoras respondem em IPP, mas não implementam todos os atributos
exigidos pelo modo ``-m everywhere``. Este serviço tenta driverless primeiro e,
quando o equipamento não é compatível, escolhe um PPD instalado e mantém o
melhor transporte disponível.
"""
from __future__ import annotations

from dataclasses import dataclass
import socket
from urllib.parse import urlparse

from .core import CupsService, PrinterManagerError, validate_device_uri, validate_queue_name


@dataclass(frozen=True, slots=True)
class InstallOutcome:
    queue_name: str
    uri: str
    model: str
    automatic_fallback: bool
    message: str


class SmartInstallService:
    """Cria filas tentando combinações compatíveis sem comandos arbitrários."""

    DRIVERLESS_ERRORS = (
        "does not support required ipp attributes",
        "unable to create ppd",
        "document formats",
        "driverless",
    )

    MODEL_PREFERENCES = (
        # HP LaserJet Pro M402/M403 quando o HPLIP fornece o modelo.
        "laserjet_pro_m402",
        "laserjet pro m402",
        "laserjet_pro_m403",
        "laserjet pro m403",
        # Fallbacks universais, na ordem mais adequada para impressoras laser.
        "generpcl",
        "generic pcl",
        "generic.ppd",
        "generic postscript",
    )

    def __init__(self, cups: CupsService | None = None) -> None:
        self.cups = cups or CupsService()

    def install(self, name: str, uri: str, model: str = "everywhere") -> InstallOutcome:
        safe_name = validate_queue_name(name)
        safe_uri = validate_device_uri(uri)
        try:
            self.cups.add_printer(safe_name, safe_uri, model)
            return InstallOutcome(
                safe_name,
                safe_uri,
                model,
                False,
                "Impressora instalada usando o modo selecionado.",
            )
        except PrinterManagerError as exc:
            if model != "everywhere" or not self._is_driverless_failure(str(exc)):
                raise
            original_error = str(exc)

        models = self._installed_models()
        fallback_models = self._rank_models(models)
        if not fallback_models:
            raise PrinterManagerError(
                "A impressora não suporta IPP Everywhere e não há um driver "
                "PCL/PostScript compatível instalado. Instale HPLIP ou escolha "
                "manualmente o driver do fabricante."
            )

        attempts: list[str] = []
        for candidate_uri in self._transport_candidates(safe_uri):
            for candidate_model in fallback_models:
                try:
                    self.cups.add_printer(safe_name, candidate_uri, candidate_model)
                    transport = urlparse(candidate_uri).scheme.upper()
                    return InstallOutcome(
                        safe_name,
                        candidate_uri,
                        candidate_model,
                        True,
                        "O equipamento não oferece IPP Everywhere completo. "
                        f"A fila foi configurada automaticamente por {transport} "
                        "com um driver compatível instalado no sistema.",
                    )
                except PrinterManagerError as exc:
                    attempts.append(f"{candidate_uri} + {candidate_model}: {exc}")

        detail = attempts[-1] if attempts else original_error
        raise PrinterManagerError(
            "Não foi possível criar a fila automaticamente. Última tentativa: " + detail
        )

    @classmethod
    def _is_driverless_failure(cls, message: str) -> bool:
        lowered = message.lower()
        return any(signature in lowered for signature in cls.DRIVERLESS_ERRORS)

    def _installed_models(self) -> list[tuple[str, str]]:
        result = self.cups.runner.run(["lpinfo", "-m"], check=False)
        models: list[tuple[str, str]] = []
        for line in result.stdout.splitlines():
            identifier, separator, description = line.partition(" ")
            if identifier and separator:
                models.append((identifier.strip(), description.strip()))
        return models

    @classmethod
    def _rank_models(cls, models: list[tuple[str, str]]) -> list[str]:
        ranked: list[str] = []
        for preference in cls.MODEL_PREFERENCES:
            for identifier, description in models:
                haystack = f"{identifier} {description}".lower()
                if preference in haystack and identifier not in ranked:
                    ranked.append(identifier)
        return ranked

    @staticmethod
    def _port_open(host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=1.5):
                return True
        except OSError:
            return False

    def _transport_candidates(self, original_uri: str) -> list[str]:
        parsed = urlparse(original_uri)
        candidates = [original_uri]
        host = parsed.hostname
        if not host:
            return candidates
        if self._port_open(host, 9100):
            candidates.append(f"socket://{host}:9100")
        if self._port_open(host, 515):
            candidates.append(f"lpd://{host}/lp")
        # Mantém a ordem e remove duplicados.
        return list(dict.fromkeys(candidates))
