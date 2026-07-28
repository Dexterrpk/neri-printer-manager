"""Backup e restauração controlada das configurações de impressão."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .core import CommandRunner, PrinterManagerError, run_admin_action


@dataclass(frozen=True, slots=True)
class BackupInfo:
    archive: Path
    manifest: Path
    created_at: str
    sha256: str


class BackupService:
    SOURCES = (
        Path("/etc/cups/cupsd.conf"),
        Path("/etc/cups/printers.conf"),
        Path("/etc/cups/ppd"),
        Path("/etc/samba/smb.conf"),
    )

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=180)

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def create(self, destination: Path) -> BackupInfo:
        if not destination.is_dir():
            raise PrinterManagerError("Escolha uma pasta existente para salvar o backup.")
        result = run_admin_action(
            self.runner,
            "create-backup",
            str(destination.resolve()),
        )
        try:
            payload = json.loads(result.stdout.splitlines()[-1])
            archive = Path(str(payload["archive_path"]))
            manifest = Path(str(payload["manifest_path"]))
            timestamp = str(payload["created_at"])
            checksum = str(payload["sha256"])
        except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise PrinterManagerError(
                "O backup foi solicitado, mas o helper não devolveu uma confirmação válida."
            ) from exc
        if not archive.is_file() or not manifest.is_file():
            raise PrinterManagerError("O arquivo de backup não foi criado corretamente.")
        return BackupInfo(archive, manifest, timestamp, checksum)

    def verify(self, archive: Path, expected_sha256: str) -> bool:
        return archive.is_file() and self._digest(archive) == expected_sha256

    @staticmethod
    def copy_for_restore(archive: Path, staging: Path) -> Path:
        """Copia o arquivo para uma área controlada antes da restauração privilegiada."""
        staging.mkdir(parents=True, exist_ok=True)
        target = staging / archive.name
        shutil.copy2(archive, target)
        return target
