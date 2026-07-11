"""Diagnóstico e planejamento de compartilhamento de impressoras."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re

from .core import CommandRunner


class SharingState(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    MISCONFIGURED = "misconfigured"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SharingCheck:
    component: str
    state: SharingState
    message: str
    remediation: str | None = None


class SharingService:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=15)

    def cups_status(self) -> SharingCheck:
        result = self.runner.run(["cupsctl"], check=False)
        if result.returncode != 0:
            return SharingCheck(
                "CUPS",
                SharingState.UNKNOWN,
                result.stderr or "Não foi possível consultar o CUPS",
            )
        settings = {
            key.strip(): value.strip()
            for line in result.stdout.splitlines()
            if "=" in line
            for key, value in [line.split("=", 1)]
        }
        shared = settings.get("_share_printers") == "1"
        remote = settings.get("_remote_any") == "1" or settings.get("_remote_admin") == "1"
        if shared:
            detail = "Compartilhamento de filas habilitado"
            if remote:
                detail += "; acesso remoto detectado"
            return SharingCheck("CUPS", SharingState.ENABLED, detail)
        return SharingCheck(
            "CUPS",
            SharingState.DISABLED,
            "Compartilhamento de filas desabilitado",
            "Habilite somente em redes confiáveis e revise as regras de acesso.",
        )

    def samba_status(self) -> SharingCheck:
        if not self.runner.exists("testparm"):
            return SharingCheck(
                "Samba",
                SharingState.DISABLED,
                "Samba não instalado",
                "Instale samba e smbclient para compartilhar com Windows.",
            )
        result = self.runner.run(["testparm", "-s"], check=False)
        if result.returncode != 0:
            return SharingCheck(
                "Samba",
                SharingState.MISCONFIGURED,
                result.stderr or result.stdout or "Configuração inválida",
                "Corrija smb.conf antes de reiniciar o serviço.",
            )
        has_printers = bool(re.search(r"^\[printers\]", result.stdout, re.MULTILINE))
        if has_printers:
            return SharingCheck("Samba", SharingState.ENABLED, "Seção [printers] válida")
        return SharingCheck(
            "Samba",
            SharingState.DISABLED,
            "Seção [printers] ausente",
            "Crie uma seção de impressão segura no smb.conf.",
        )

    def configuration_files(self) -> dict[str, bool]:
        return {
            "/etc/cups/cupsd.conf": Path("/etc/cups/cupsd.conf").is_file(),
            "/etc/samba/smb.conf": Path("/etc/samba/smb.conf").is_file(),
        }

    def audit(self) -> list[SharingCheck]:
        return [self.cups_status(), self.samba_status()]
