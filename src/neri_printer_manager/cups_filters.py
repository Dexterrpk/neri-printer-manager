"""Diagnóstico de falhas de filtros, backends e PPDs do CUPS."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import os
import re

from .core import CommandRunner, Severity


class RepairAction(str, Enum):
    REINSTALL_FILTERS = "reinstall_filters"
    REINSTALL_GHOSTSCRIPT = "reinstall_ghostscript"
    CHECK_PPD = "check_ppd"
    CHECK_PERMISSIONS = "check_permissions"
    RESTART_CUPS = "restart_cups"
    CHECK_BACKEND = "check_backend"


@dataclass(frozen=True, slots=True)
class FilterFinding:
    code: str
    title: str
    severity: Severity
    evidence: str
    actions: tuple[RepairAction, ...]


_SIGNATURES: tuple[tuple[re.Pattern[str], str, str, tuple[RepairAction, ...]], ...] = (
    (
        re.compile(r"filter failed", re.IGNORECASE),
        "filter_failed",
        "Filtro de impressão falhou",
        (
            RepairAction.REINSTALL_FILTERS,
            RepairAction.REINSTALL_GHOSTSCRIPT,
            RepairAction.RESTART_CUPS,
        ),
    ),
    (
        re.compile(r"unable to open ppd|ppd.*(missing|not found)", re.IGNORECASE),
        "ppd_missing",
        "PPD ausente ou ilegível",
        (RepairAction.CHECK_PPD, RepairAction.CHECK_PERMISSIONS),
    ),
    (
        re.compile(r"permission denied", re.IGNORECASE),
        "permission_denied",
        "Permissão negada em filtro ou backend",
        (RepairAction.CHECK_PERMISSIONS, RepairAction.RESTART_CUPS),
    ),
    (
        re.compile(r"ghostscript|gs:.*error", re.IGNORECASE),
        "ghostscript_failed",
        "Falha no Ghostscript",
        (RepairAction.REINSTALL_GHOSTSCRIPT, RepairAction.RESTART_CUPS),
    ),
    (
        re.compile(r"backend failed|backend.*(not found|stopped)", re.IGNORECASE),
        "backend_failed",
        "Backend de comunicação falhou",
        (RepairAction.CHECK_BACKEND, RepairAction.CHECK_PERMISSIONS, RepairAction.RESTART_CUPS),
    ),
    (
        re.compile(r"broken pipe", re.IGNORECASE),
        "broken_pipe",
        "Comunicação interrompida durante a impressão",
        (RepairAction.CHECK_BACKEND, RepairAction.RESTART_CUPS),
    ),
)


class CupsFilterService:
    FILTER_DIRS = (Path("/usr/lib/cups/filter"), Path("/usr/lib/cups/backend"))

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout=20)

    @staticmethod
    def analyze_text(text: str) -> list[FilterFinding]:
        findings: dict[str, FilterFinding] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            for pattern, code, title, actions in _SIGNATURES:
                if pattern.search(line):
                    findings.setdefault(
                        code,
                        FilterFinding(code, title, Severity.ERROR, line[:500], actions),
                    )
        return list(findings.values())

    def read_recent_errors(self, lines: int = 400) -> str:
        """Lê o log via journalctl e usa error_log como fallback."""
        journal = self.runner.run(
            ["journalctl", "-u", "cups.service", "-n", str(lines), "--no-pager"],
            check=False,
        )
        chunks = [journal.stdout]
        error_log = Path("/var/log/cups/error_log")
        if error_log.is_file() and os.access(error_log, os.R_OK):
            try:
                chunks.append("\n".join(error_log.read_text(errors="replace").splitlines()[-lines:]))
            except OSError:
                pass
        return "\n".join(item for item in chunks if item)

    def diagnose(self) -> list[FilterFinding]:
        findings = self.analyze_text(self.read_recent_errors())
        findings.extend(self._filesystem_findings())
        unique: dict[str, FilterFinding] = {}
        for item in findings:
            unique.setdefault(item.code, item)
        return list(unique.values())

    def _filesystem_findings(self) -> list[FilterFinding]:
        findings: list[FilterFinding] = []
        for directory in self.FILTER_DIRS:
            if not directory.is_dir():
                findings.append(
                    FilterFinding(
                        f"missing_dir:{directory}",
                        f"Diretório do CUPS ausente: {directory}",
                        Severity.ERROR,
                        str(directory),
                        (RepairAction.REINSTALL_FILTERS,),
                    )
                )
                continue
            bad_files: list[str] = []
            try:
                for entry in directory.iterdir():
                    if entry.is_file() and not os.access(entry, os.X_OK):
                        bad_files.append(entry.name)
            except OSError as exc:
                findings.append(
                    FilterFinding(
                        f"unreadable_dir:{directory}",
                        "Não foi possível verificar os filtros",
                        Severity.WARNING,
                        str(exc),
                        (RepairAction.CHECK_PERMISSIONS,),
                    )
                )
            if bad_files:
                findings.append(
                    FilterFinding(
                        f"non_executable:{directory}",
                        "Filtros ou backends sem permissão de execução",
                        Severity.ERROR,
                        ", ".join(sorted(bad_files)[:20]),
                        (RepairAction.CHECK_PERMISSIONS, RepairAction.RESTART_CUPS),
                    )
                )
        return findings

    @staticmethod
    def packages_for(actions: tuple[RepairAction, ...]) -> list[str]:
        packages: set[str] = set()
        if RepairAction.REINSTALL_FILTERS in actions:
            packages.update(("cups-filters", "cups", "cups-client"))
        if RepairAction.REINSTALL_GHOSTSCRIPT in actions:
            packages.add("ghostscript")
        return sorted(packages)
