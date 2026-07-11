"""Geração de relatórios técnicos e pacotes de suporte."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import json
import platform
import shutil
import subprocess
import zipfile

from .core import CupsService, DiagnosticService, JobService
from .cups_filters import CupsFilterService
from .dependencies import DependencyService
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
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return (result.stdout or result.stderr).strip()

    def collect(self) -> dict[str, object]:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "system": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "kernel": platform.release(),
                "hostname": platform.node(),
                "os_release": self._command_output(["cat", "/etc/os-release"]),
            },
            "printers": [asdict(item) for item in CupsService().list_printers()],
            "jobs": [asdict(item) for item in JobService().list_jobs()],
            "diagnostics": [asdict(item) for item in DiagnosticService().run_all()],
            "dependencies": [asdict(item) for item in DependencyService().audit()],
            "filters": [asdict(item) for item in CupsFilterService().diagnose()],
            "sharing": [asdict(item) for item in SharingService().audit()],
        }

    def write_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.collect(), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
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
        return path

    def create_support_bundle(self, destination: Path) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        work = destination / f"neri-support-{stamp}"
        work.mkdir(parents=True, exist_ok=True)

        self.write_json(work / "report.json")
        self.write_html(work / "report.html")

        candidates = (
            Path.home() / ".local/state/neri-printer-manager/application.log",
            Path("/var/log/cups/error_log"),
            Path("/var/log/cups/access_log"),
            Path("/var/log/cups/page_log"),
        )
        logs = work / "logs"
        logs.mkdir(exist_ok=True)
        for source in candidates:
            if source.is_file():
                try:
                    shutil.copy2(source, logs / source.name)
                except OSError:
                    pass

        archive = destination / f"neri-support-{stamp}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for item in work.rglob("*"):
                if item.is_file():
                    bundle.write(item, item.relative_to(work))
        shutil.rmtree(work, ignore_errors=True)
        return archive
