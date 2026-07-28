"""Diagnóstico e planejamento de compartilhamento de impressoras."""

from __future__ import annotations

import getpass
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .core import (
    CommandRunner,
    PrinterManagerError,
    run_admin_action,
    validate_queue_name,
)
from .security import contains_control_characters


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
        remote_any = settings.get("_remote_any") == "1"
        remote_admin = settings.get("_remote_admin") == "1"
        if remote_any or remote_admin:
            return SharingCheck(
                "CUPS",
                SharingState.MISCONFIGURED,
                "O CUPS permite acesso ou administração além da política local",
                "Compartilhe novamente uma fila para limitar o serviço à rede local.",
            )
        if shared:
            return SharingCheck(
                "CUPS",
                SharingState.ENABLED,
                "Compartilhamento de filas habilitado para a política local",
            )
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
        section_match = re.search(
            r"(?ims)^\s*\[printers\]\s*$\n(?P<body>.*?)(?=^\s*\[[^]]+\]\s*$|\Z)",
            result.stdout,
        )
        if section_match:
            body = section_match.group("body")
            guest_enabled = bool(re.search(r"(?im)^\s*guest ok\s*=\s*(?:yes|true|1)\s*$", body))
            printable = bool(re.search(r"(?im)^\s*printable\s*=\s*(?:yes|true|1)\s*$", body))
            if guest_enabled or not printable:
                return SharingCheck(
                    "Samba",
                    SharingState.MISCONFIGURED,
                    "A seção [printers] permite convidado ou não está imprimível",
                    "Compartilhe novamente uma fila para aplicar os parâmetros seguros.",
                )
            return SharingCheck("Samba", SharingState.ENABLED, "Seção [printers] válida")
        return SharingCheck(
            "Samba",
            SharingState.DISABLED,
            "Seção [printers] ausente",
            "Crie uma seção de impressão segura no smb.conf.",
        )

    def samba_user_status(self, username: str | None = None) -> SharingCheck:
        user = username or getpass.getuser()
        if not self.runner.exists("pdbedit"):
            return SharingCheck(
                "Usuário Samba",
                SharingState.DISABLED,
                "Ferramenta de usuários Samba não instalada",
                "Instale samba-common-bin.",
            )
        result = self.runner.run(["pdbedit", "-L"], check=False)
        if result.returncode != 0:
            return SharingCheck(
                "Usuário Samba",
                SharingState.UNKNOWN,
                "O Samba não permitiu consultar as contas sem autorização administrativa",
                "Se necessário, defina ou atualize sua senha Samba abaixo.",
            )
        configured = any(
            line.split(":", 1)[0] == user for line in result.stdout.splitlines() if ":" in line
        )
        if configured:
            return SharingCheck(
                "Usuário Samba",
                SharingState.ENABLED,
                f"A conta {user} está preparada para autenticação pelo Windows",
            )
        return SharingCheck(
            "Usuário Samba",
            SharingState.DISABLED,
            f"A conta {user} ainda não possui senha de acesso Samba",
            "Defina uma senha Samba na tela de compartilhamento; ela não será salva pelo programa.",
        )

    def firewall_status(self) -> SharingCheck:
        if not self.runner.exists("ufw"):
            return SharingCheck(
                "Firewall",
                SharingState.UNKNOWN,
                "UFW não instalado; pode existir outro firewall na rede",
                "Se outro computador não conectar, confirme as portas 631, 139 e 445.",
            )
        result = self.runner.run(["systemctl", "is-active", "ufw.service"], check=False)
        if result.stdout != "active":
            return SharingCheck(
                "Firewall",
                SharingState.DISABLED,
                "UFW inativo neste computador",
            )
        return SharingCheck(
            "Firewall",
            SharingState.UNKNOWN,
            "UFW ativo; as regras não são alteradas automaticamente",
            "Autorize os perfis CUPS e Samba somente para a rede local confiável.",
        )

    def enable_queue(self, queue: str) -> str:
        safe_queue = validate_queue_name(queue)
        run_admin_action(self.runner, "enable-printer-sharing", safe_queue)
        return (
            f"A fila {safe_queue} foi compartilhada pelo CUPS e preparada no Samba. "
            "Use uma conta Samba configurada para acessar pelo Windows."
        )

    def disable_queue(self, queue: str) -> str:
        safe_queue = validate_queue_name(queue)
        run_admin_action(self.runner, "disable-printer-sharing", safe_queue)
        return f"O compartilhamento da fila {safe_queue} foi desativado."

    def configure_samba_password(self, username: str, password: str) -> str:
        user = username.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", user):
            raise PrinterManagerError("Nome de usuário local inválido.")
        if not 8 <= len(password) <= 256 or contains_control_characters(password):
            raise PrinterManagerError("A senha Samba deve ter entre 8 e 256 caracteres válidos.")
        run_admin_action(
            self.runner,
            "set-samba-password",
            user,
            input_text=f"{password}\n",
        )
        return f"A conta {user} está pronta para autenticação de impressão pelo Windows."

    def configuration_files(self) -> dict[str, bool]:
        return {
            "/etc/cups/cupsd.conf": Path("/etc/cups/cupsd.conf").is_file(),
            "/etc/samba/smb.conf": Path("/etc/samba/smb.conf").is_file(),
        }

    def audit(self) -> list[SharingCheck]:
        return [
            self.cups_status(),
            self.samba_status(),
            self.samba_user_status(),
            self.firewall_status(),
        ]
