from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from lean_prefix.audit import AuditError, audit_manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lean-prefix")
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit", help="verify an immutable rollout manifest")
    audit.add_argument("--manifest", type=Path, required=True)
    audit.add_argument("--source-root", type=Path)
    audit.add_argument("--output", type=Path, help="optional report path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "audit":
            report = audit_manifest(args.manifest, args.source_root)
            rendered = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
            if args.output:
                args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
    except (AuditError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 2

