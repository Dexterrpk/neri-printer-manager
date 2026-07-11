"""Auditoria de pacotes necessários no Linux Mint/Ubuntu.

O módulo apenas detecta e planeja. A instalação é delegada ao helper privilegiado,
que aceita somente pacotes previamente autorizados.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from .core import CommandRunner, PrinterManagerError


class PackageState(str, Enum):
    INSTALLED = "installed"
    MISSING = "missing"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PackageRequirement:
    name: str
    reason: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class PackageStatus:
    requirement: PackageRequirement
    state: PackageState
    version: str | None = None


CORE_PACKAGES: tuple[PackageRequirement, ...] = (
    PackageRequirement("cups", "Servidor de impressão CUPS"),
    PackageRequirement("cups-client", "Ferramentas lpstat, lpadmin e lp"),
    PackageRequirement("cups-browsed", "Descoberta e filas remotas"),
    PackageRequirement("cups-filters", "Filtros modernos de impressão"),
    PackageRequirement("ghostscript", "Conversão PostScript/PDF"),
    PackageRequirement("avahi-daemon", "Descoberta mDNS/Bonjour"),
    PackageRequirement("avahi-utils", "Ferramentas de diagnóstico mDNS"),
    PackageRequirement("policykit-1", "Autorização administrativa segura"),
    PackageRequirement("samba", "Compartilhamento com Windows", required=False),
    PackageRequirement("smbclient", "Diagnóstico de compartilhamentos SMB", required=False),
    PackageRequirement("printer-driver-gutenprint", "Drivers genéricos Gutenprint", required=False),
    PackageRequirement("foomatic-db-compressed-ppds", "Base adicional de PPDs", required=False),
)

_ALLOWED_PACKAGE = re.compile(r"^[a-z0-9][a-z0-9+.-]{0,99}$")


class DependencyService:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=20)

    def status(self, requirement: PackageRequirement) -> PackageStatus:
        if not _ALLOWED_PACKAGE.fullmatch(requirement.name):
            raise PrinterManagerError("Nome de pacote inválido no catálogo interno.")
        result = self.runner.run(
            ["dpkg-query", "-W", "-f=${Status}\t${Version}", requirement.name],
            check=False,
        )
        if result.returncode == 0 and result.stdout.startswith("install ok installed"):
            _, _, version = result.stdout.partition("\t")
            return PackageStatus(requirement, PackageState.INSTALLED, version or None)
        if result.returncode == 1:
            return PackageStatus(requirement, PackageState.MISSING)
        return PackageStatus(requirement, PackageState.UNKNOWN)

    def audit(self) -> list[PackageStatus]:
        return [self.status(item) for item in CORE_PACKAGES]

    def missing(self, *, include_optional: bool = False) -> list[str]:
        packages: list[str] = []
        for item in self.audit():
            if item.state is not PackageState.MISSING:
                continue
            if item.requirement.required or include_optional:
                packages.append(item.requirement.name)
        return packages

    @staticmethod
    def build_install_request(packages: list[str]) -> list[str]:
        """Valida uma solicitação antes de enviá-la ao helper."""
        allowed = {item.name for item in CORE_PACKAGES}
        normalized = sorted(set(packages))
        if not normalized:
            raise PrinterManagerError("Nenhum pacote foi selecionado.")
        if any(package not in allowed for package in normalized):
            raise PrinterManagerError("A solicitação contém pacote não autorizado.")
        return normalized
