"""Backup e restauração controlada das configurações de impressão."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import tarfile


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

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def create(self, destination: Path) -> BackupInfo:
        destination.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive = destination / f"neri-printer-backup-{timestamp}.tar.gz"
        existing = [path for path in self.SOURCES if path.exists()]
        with tarfile.open(archive, "w:gz") as tar:
            for source in existing:
                tar.add(source, arcname=str(source).lstrip("/"), recursive=True)
        checksum = self._digest(archive)
        manifest = archive.with_suffix(archive.suffix + ".json")
        manifest.write_text(
            json.dumps(
                {
                    "created_at": timestamp,
                    "archive": archive.name,
                    "sha256": checksum,
                    "sources": [str(path) for path in existing],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
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
