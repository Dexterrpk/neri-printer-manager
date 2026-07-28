"""Diagnóstico atual e verificável de filtros, backends e PPDs do CUPS."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from .core import CommandRunner, Severity
from .security import redact_text


class RepairAction(str, Enum):
    REINSTALL_FILTERS = "reinstall_filters"
    REINSTALL_GHOSTSCRIPT = "reinstall_ghostscript"
    CHECK_PPD = "check_ppd"
    FIX_PERMISSIONS = "fix_permissions"
    RESTART_CUPS = "restart_cups"
    CHECK_BACKEND = "check_backend"
    CLEAR_STALE_JOBS = "clear_stale_jobs"


@dataclass(frozen=True, slots=True)
class FilterFinding:
    code: str
    title: str
    severity: Severity
    evidence: str
    actions: tuple[RepairAction, ...]
    source: str = "CUPS"
    current: bool = True


_SIGNATURES: tuple[tuple[re.Pattern[str], str, str, tuple[RepairAction, ...]], ...] = (
    (
        re.compile(r"filter failed|stopped with status [^0]", re.IGNORECASE),
        "filter_failed",
        "Filtro falhou em trabalho recente",
        (
            RepairAction.REINSTALL_FILTERS,
            RepairAction.REINSTALL_GHOSTSCRIPT,
            RepairAction.RESTART_CUPS,
        ),
    ),
    (
        re.compile(r"unable to open ppd|ppd.*(missing|not found|bad value)", re.IGNORECASE),
        "ppd_missing",
        "Arquivo PPD ausente ou inválido",
        (RepairAction.CHECK_PPD,),
    ),
    (
        re.compile(r"permission denied", re.IGNORECASE),
        "permission_denied",
        "Permissão incorreta em filtro ou backend",
        (RepairAction.FIX_PERMISSIONS, RepairAction.RESTART_CUPS),
    ),
    (
        re.compile(r"ghostscript|gs:.*error", re.IGNORECASE),
        "ghostscript_failed",
        "Falha confirmada no Ghostscript",
        (RepairAction.REINSTALL_GHOSTSCRIPT, RepairAction.RESTART_CUPS),
    ),
    (
        re.compile(r"backend failed|backend.*(not found|stopped|exited)", re.IGNORECASE),
        "backend_failed",
        "Backend de comunicação falhou",
        (RepairAction.CHECK_BACKEND, RepairAction.RESTART_CUPS),
    ),
    (
        re.compile(r"broken pipe|unable to connect|connection refused", re.IGNORECASE),
        "communication_failed",
        "Comunicação com a impressora foi interrompida",
        (RepairAction.CHECK_BACKEND,),
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
                        FilterFinding(
                            code,
                            title,
                            Severity.ERROR,
                            redact_text(line[:500]),
                            actions,
                            "Log recente",
                        ),
                    )
        return list(findings.values())

    def read_recent_errors(self, minutes: int = 30, lines: int = 250) -> str:
        journal = self.runner.run(
            [
                "journalctl",
                "-u",
                "cups.service",
                "--since",
                f"-{minutes} minutes",
                "-n",
                str(lines),
                "--no-pager",
                "-p",
                "warning..alert",
            ],
            check=False,
        )
        chunks = [journal.stdout]
        error_log = Path("/var/log/cups/error_log")
        if error_log.is_file() and os.access(error_log, os.R_OK):
            try:
                recent = error_log.read_text(errors="replace").splitlines()[-lines:]
                chunks.append(
                    "\n".join(
                        line
                        for line in recent
                        if re.search(r"\bE\s|\[Job \d+\].*(failed|error)", line, re.IGNORECASE)
                        and self._line_is_recent(line, minutes)
                    )
                )
            except OSError:
                pass
        return redact_text("\n".join(item for item in chunks if item))

    @staticmethod
    def _line_is_recent(line: str, minutes: int) -> bool:
        """Evita que um erro antigo na cauda do ``error_log`` pareça atual."""

        match = re.search(
            r"\[(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-]\d{4})\]",
            line,
        )
        if not match:
            return False
        day, month_name, year, hour, minute, second, offset = match.groups()
        months = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        month = months.get(month_name.lower())
        if month is None:
            return False
        sign = 1 if offset[0] == "+" else -1
        utc_offset = timedelta(
            hours=sign * int(offset[1:3]),
            minutes=sign * int(offset[3:5]),
        )
        try:
            timestamp = datetime(
                int(year),
                month,
                int(day),
                int(hour),
                int(minute),
                int(second),
                tzinfo=timezone(utc_offset),
            )
        except ValueError:
            return False
        age = datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)
        return timedelta(0) <= age <= timedelta(minutes=max(1, minutes))

    def diagnose(self) -> list[FilterFinding]:
        findings = self.analyze_text(self.read_recent_errors())
        findings.extend(self._filesystem_findings())
        findings.extend(self._package_findings())
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
                        f"Diretório obrigatório ausente: {directory}",
                        Severity.ERROR,
                        str(directory),
                        (RepairAction.REINSTALL_FILTERS,),
                        "Sistema de arquivos",
                    )
                )
                continue
            bad_files: list[str] = []
            try:
                for entry in directory.iterdir():
                    if entry.is_file() and not entry.is_symlink() and not os.access(entry, os.X_OK):
                        bad_files.append(entry.name)
            except OSError as exc:
                findings.append(
                    FilterFinding(
                        f"unreadable_dir:{directory}",
                        "Não foi possível verificar diretório do CUPS",
                        Severity.WARNING,
                        str(exc),
                        (),
                        "Sistema de arquivos",
                    )
                )
            if bad_files:
                findings.append(
                    FilterFinding(
                        f"non_executable:{directory}",
                        "Filtros ou backends sem permissão de execução",
                        Severity.ERROR,
                        ", ".join(sorted(bad_files)[:20]),
                        (RepairAction.FIX_PERMISSIONS, RepairAction.RESTART_CUPS),
                        "Sistema de arquivos",
                    )
                )
        return findings

    def _package_findings(self) -> list[FilterFinding]:
        findings: list[FilterFinding] = []
        for package, action, title in (
            ("cups-filters", RepairAction.REINSTALL_FILTERS, "Pacote cups-filters ausente"),
            ("ghostscript", RepairAction.REINSTALL_GHOSTSCRIPT, "Ghostscript ausente"),
        ):
            result = self.runner.run(["dpkg-query", "-W", "-f=${Status}", package], check=False)
            if result.returncode != 0 or "install ok installed" not in result.stdout:
                findings.append(
                    FilterFinding(
                        f"package_missing:{package}",
                        title,
                        Severity.ERROR,
                        package,
                        (action,),
                        "Pacotes",
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
