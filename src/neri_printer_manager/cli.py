"""CLI para suporte remoto e automação."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .backup import BackupService
from .core import CupsService, DiagnosticService, DiscoveryService, JobService
from .cups_filters import CupsFilterService
from .dependencies import DependencyService
from .network import NetworkService
from .repair import RepairService
from .reports import ReportService
from .sharing import SharingService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="neri-printer-cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    commands.add_parser("jobs")
    commands.add_parser("discover")
    commands.add_parser("diagnose")
    commands.add_parser("dependencies")
    commands.add_parser("filters")
    commands.add_parser("sharing")
    add = commands.add_parser("add")
    add.add_argument("--name", required=True)
    add.add_argument("--uri", required=True)
    add.add_argument("--model", default="everywhere")
    remove = commands.add_parser("remove")
    remove.add_argument("name")
    cancel = commands.add_parser("cancel")
    cancel.add_argument("job_id")
    scan = commands.add_parser("scan")
    scan.add_argument("host")
    backup = commands.add_parser("backup")
    backup.add_argument("destination", type=Path)
    repair_deps = commands.add_parser("repair-dependencies")
    repair_deps.add_argument("--optional", action="store_true")
    report = commands.add_parser("report")
    report.add_argument("path", type=Path)
    report.add_argument("--format", choices=("json", "html"), default="json")
    support = commands.add_parser("support-bundle")
    support.add_argument("destination", type=Path)
    return parser


def dump(items: object) -> None:
    print(json.dumps(items, ensure_ascii=False, indent=2, default=str))


def main() -> int:
    args = build_parser().parse_args()
    cups = CupsService()
    if args.command == "list":
        dump([asdict(item) for item in cups.list_printers()])
    elif args.command == "jobs":
        dump([asdict(item) for item in JobService().list_jobs()])
    elif args.command == "discover":
        dump([asdict(item) for item in DiscoveryService().discover()])
    elif args.command == "diagnose":
        dump([asdict(item) for item in DiagnosticService().run_all()])
    elif args.command == "dependencies":
        dump([asdict(item) for item in DependencyService().audit()])
    elif args.command == "filters":
        dump([asdict(item) for item in CupsFilterService().diagnose()])
    elif args.command == "sharing":
        dump([asdict(item) for item in SharingService().audit()])
    elif args.command == "add":
        cups.add_printer(args.name, args.uri, args.model)
    elif args.command == "remove":
        cups.remove_printer(args.name)
    elif args.command == "cancel":
        JobService().cancel(args.job_id)
    elif args.command == "scan":
        dump([asdict(item) for item in NetworkService().scan_printer_ports(args.host)])
    elif args.command == "backup":
        dump(asdict(BackupService().create(args.destination)))
    elif args.command == "repair-dependencies":
        dump(asdict(RepairService().install_missing_dependencies(args.optional)))
    elif args.command == "report":
        service = ReportService()
        target = service.write_html(args.path) if args.format == "html" else service.write_json(args.path)
        print(target)
    elif args.command == "support-bundle":
        print(ReportService().create_support_bundle(args.destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
