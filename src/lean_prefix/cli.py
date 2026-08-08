from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from lean_prefix.audit import AuditError, audit_manifest
from lean_prefix.analysis import analyze_exact
from lean_prefix.native import NativeExtractionError, extract_and_analyze
from lean_prefix.review import ReviewSelectionError, select_review_sample


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lean-prefix")
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit", help="verify an immutable rollout manifest")
    audit.add_argument("--manifest", type=Path, required=True)
    audit.add_argument("--source-root", type=Path)
    audit.add_argument("--output", type=Path, help="optional report path")
    exact = commands.add_parser("analyze-exact", help="measure exact whole-proof reuse")
    exact.add_argument("--manifest", type=Path, required=True)
    exact.add_argument("--source-root", type=Path)
    exact.add_argument("--output", type=Path, help="optional report path")
    native = commands.add_parser("analyze-native", help="measure Lean-native exact prefix reuse")
    native.add_argument("--manifest", type=Path, required=True)
    native.add_argument("--source-root", type=Path)
    native.add_argument("--lean-workspace", type=Path, required=True)
    native.add_argument("--extractor", type=Path, default=Path("lean/LeanPrefix/Extract.lean"))
    native.add_argument("--artifact", type=Path, required=True)
    native.add_argument("--output", type=Path, help="optional aggregate report path")
    native.add_argument("--limit", type=int)
    native.add_argument("--progress-every", type=int, default=10_000)
    review = commands.add_parser("select-review", help="select deterministic hand-review cases")
    review.add_argument("--manifest", type=Path, required=True)
    review.add_argument("--source-root", type=Path)
    review.add_argument("--artifact", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "audit":
            report = audit_manifest(args.manifest, args.source_root)
            rendered = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
        if args.command == "analyze-exact":
            report = analyze_exact(args.manifest, args.source_root)
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
        if args.command == "analyze-native":
            report = extract_and_analyze(
                args.manifest,
                lean_workspace=args.lean_workspace,
                extractor_path=args.extractor,
                artifact_path=args.artifact,
                source_root=args.source_root,
                limit=args.limit,
                progress_every=args.progress_every,
            )
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
        if args.command == "select-review":
            report = select_review_sample(args.manifest, args.artifact, args.source_root)
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
    except (AuditError, NativeExtractionError, ReviewSelectionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 2
