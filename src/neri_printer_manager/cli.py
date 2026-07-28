"""CLI para suporte remoto e automação."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .backup import BackupService
from .core import (
    CupsService,
    DiagnosticService,
    DiscoveryService,
    JobService,
    PrinterManagerError,
)
from .cups_filters import CupsFilterService
from .dependencies import DependencyService
from .health import PrinterHealthService
from .network import NetworkService
from .repair import RepairService
from .reports import ReportService
from .security import redact_data, redact_text
from .sharing import SharingService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="neri-printer-cli")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    list_command = commands.add_parser("list")
    list_command.add_argument("--all", action="store_true", dest="include_automatic")
    commands.add_parser("jobs")
    commands.add_parser("discover")
    commands.add_parser("diagnose")
    commands.add_parser("dependencies")
    commands.add_parser("filters")
    commands.add_parser("sharing")
    commands.add_parser("health")
    add = commands.add_parser("add")
    add.add_argument("--name", required=True)
    add.add_argument("--uri", required=True)
    add.add_argument("--model", default="everywhere")
    add.add_argument(
        "--username",
        help="Usuário SMB; a senha será solicitada sem aparecer no histórico",
    )
    remove = commands.add_parser("remove")
    remove.add_argument("name")
    default = commands.add_parser("set-default")
    default.add_argument("name")
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
    share = commands.add_parser("share")
    share.add_argument("name")
    unshare = commands.add_parser("unshare")
    unshare.add_argument("name")
    samba_password = commands.add_parser("samba-password")
    samba_password.add_argument("--user", default=getpass.getuser())
    return parser


def dump(items: object) -> None:
    print(json.dumps(redact_data(items), ensure_ascii=False, indent=2, default=str))


def _main() -> int:
    args = build_parser().parse_args()
    cups = CupsService()
    if args.command == "list":
        dump(
            [asdict(item) for item in cups.list_printers(include_automatic=args.include_automatic)]
        )
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
    elif args.command == "health":
        dump([asdict(item) for item in PrinterHealthService().run_all()])
    elif args.command == "add":
        if cups.queue_exists(args.name):
            raise PrinterManagerError(
                f"A fila {args.name} já existe. Remova-a explicitamente antes de substituir."
            )
        if args.username:
            password = getpass.getpass("Senha do compartilhamento SMB: ")
            cups.add_authenticated_printer(
                args.name,
                args.uri,
                args.model,
                args.username,
                password,
            )
        else:
            cups.add_printer(args.name, args.uri, args.model)
    elif args.command == "remove":
        cups.remove_printer(args.name)
    elif args.command == "set-default":
        cups.set_default(args.name)
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
        target = (
            service.write_html(args.path)
            if args.format == "html"
            else service.write_json(args.path)
        )
        print(target)
    elif args.command == "support-bundle":
        print(ReportService().create_support_bundle(args.destination))
    elif args.command == "share":
        print(SharingService().enable_queue(args.name))
    elif args.command == "unshare":
        print(SharingService().disable_queue(args.name))
    elif args.command == "samba-password":
        first = getpass.getpass("Nova senha Samba: ")
        second = getpass.getpass("Confirme a senha Samba: ")
        if first != second:
            raise PrinterManagerError("As senhas não conferem.")
        print(SharingService().configure_samba_password(args.user, first))
    return 0


def main() -> int:
    try:
        return _main()
    except PrinterManagerError as exc:
        print(f"Erro: {redact_text(exc)}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Operação cancelada.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
