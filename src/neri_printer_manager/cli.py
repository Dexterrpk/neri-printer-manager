"""CLI para suporte remoto e automação."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .core import CupsService, DiagnosticService, DiscoveryService, write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="neri-printer-cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    commands.add_parser("discover")
    commands.add_parser("diagnose")
    add = commands.add_parser("add")
    add.add_argument("--name", required=True)
    add.add_argument("--uri", required=True)
    add.add_argument("--model", default="everywhere")
    remove = commands.add_parser("remove")
    remove.add_argument("name")
    report = commands.add_parser("report")
    report.add_argument("path", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    cups = CupsService()
    if args.command == "list":
        print(json.dumps([asdict(item) for item in cups.list_printers()], ensure_ascii=False, indent=2))
    elif args.command == "discover":
        print(json.dumps([asdict(item) for item in DiscoveryService().discover()], ensure_ascii=False, indent=2))
    elif args.command == "diagnose":
        print(json.dumps([asdict(item) for item in DiagnosticService().run_all()], ensure_ascii=False, indent=2))
    elif args.command == "add":
        cups.add_printer(args.name, args.uri, args.model)
    elif args.command == "remove":
        cups.remove_printer(args.name)
    elif args.command == "report":
        write_report(args.path, cups.list_printers(), DiagnosticService().run_all())
        print(args.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
