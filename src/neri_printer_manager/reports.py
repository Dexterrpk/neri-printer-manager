"""Geração de relatórios técnicos e pacotes de suporte."""

from __future__ import annotations

import json
import platform
import subprocess
import tempfile
import zipfile
from collections import deque
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from .core import SAFE_COMMAND_PATH, CupsService, DiagnosticService, JobService
from .cups_filters import CupsFilterService
from .dependencies import DependencyService
from .security import redact_data, redact_text
from .sharing import SharingService


class ReportService:
    """Coleta informações sem alterar o sistema."""

    @staticmethod
    def _command_output(args: list[str]) -> str:
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                env={"PATH": SAFE_COMMAND_PATH, "LC_ALL": "C", "LANG": "C"},
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return redact_text((result.stdout or result.stderr).strip())

    @staticmethod
    def _safe_collect(function: Callable[[], object]) -> object:
        """Mantém o relatório utilizável mesmo quando um componente está parado."""

        try:
            return redact_data(function())
        except Exception as exc:  # noqa: BLE001 - relatório parcial deve continuar utilizável
            return {
                "available": False,
                "error": redact_text(exc),
            }

    def collect(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "system": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "kernel": platform.release(),
                "hostname": platform.node(),
                "os_release": self._command_output(["cat", "/etc/os-release"]),
            },
            "printers": self._safe_collect(
                lambda: [
                    asdict(item) for item in CupsService().list_printers(include_automatic=True)
                ]
            ),
            "jobs": self._safe_collect(lambda: [asdict(item) for item in JobService().list_jobs()]),
            "diagnostics": self._safe_collect(
                lambda: [asdict(item) for item in DiagnosticService().run_all()]
            ),
            "dependencies": self._safe_collect(
                lambda: [asdict(item) for item in DependencyService().audit()]
            ),
            "filters": self._safe_collect(
                lambda: [asdict(item) for item in CupsFilterService().diagnose()]
            ),
            "sharing": self._safe_collect(
                lambda: [asdict(item) for item in SharingService().audit()]
            ),
        }
        sanitized = redact_data(payload)
        if not isinstance(sanitized, dict):
            raise TypeError("Falha interna ao sanitizar o relatório.")
        return {str(key): value for key, value in sanitized.items()}

    def write_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.collect(), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        path.chmod(0o600)
        return path

    def write_html(self, path: Path) -> Path:
        data = self.collect()
        sections: list[str] = []
        for title, content in data.items():
            rendered = escape(json.dumps(content, ensure_ascii=False, indent=2, default=str))
            sections.append(f"<section><h2>{escape(title)}</h2><pre>{rendered}</pre></section>")
        html = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Relatório Neri Printer Manager</title>
<style>
body{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}
section{border:1px solid #ccc;border-radius:8px;padding:1rem;margin:1rem 0}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f6f6;padding:1rem;border-radius:6px}
</style></head><body><h1>Relatório Técnico — Neri Printer Manager</h1>"""
        html += "".join(sections) + "</body></html>"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        path.chmod(0o600)
        return path

    def create_support_bundle(self, destination: Path) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        archive = destination / f"neri-support-{stamp}.zip"
        with tempfile.TemporaryDirectory(prefix=".neri-support-", dir=destination) as temporary:
            work = Path(temporary)
            self.write_json(work / "report.json")
            self.write_html(work / "report.html")

            candidates = (
                Path.home() / ".local/state/neri-printer-manager/application.log",
                Path("/var/log/cups/error_log"),
                Path("/var/log/cups/access_log"),
                Path("/var/log/cups/page_log"),
            )
            logs = work / "logs"
            logs.mkdir(mode=0o700, exist_ok=True)
            for source in candidates:
                self._copy_redacted_log(source, logs / source.name)

            with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
                for item in work.rglob("*"):
                    if item.is_file():
                        bundle.write(item, item.relative_to(work))
        archive.chmod(0o600)
        return archive

    @staticmethod
    def _copy_redacted_log(source: Path, target: Path, *, max_lines: int = 2500) -> None:
        """Copia apenas a cauda do log e remove URIs autenticadas/senhas."""

        if not source.is_file():
            return
        try:
            with source.open("r", encoding="utf-8", errors="replace") as handle:
                lines = deque(handle, maxlen=max_lines)
            target.write_text(
                redact_text("".join(lines)),
                encoding="utf-8",
            )
            target.chmod(0o600)
        except OSError:
            return
