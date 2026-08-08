from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from lean_prefix.audit import AuditError, audit_manifest
from lean_prefix.analysis import analyze_exact
from lean_prefix.native import NativeExtractionError, extract_and_analyze
from lean_prefix.profile import ReplayProfileError, profile_replay_shard
from lean_prefix.profile_summary import ProfileSummaryError, summarize_replay_profiles
from lean_prefix.repl import ReplError
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
    replay = commands.add_parser("profile-replay", help="measure reached tactic costs")
    replay.add_argument("--manifest", type=Path, required=True)
    replay.add_argument("--source-root", type=Path)
    replay.add_argument("--native-artifact", type=Path, required=True)
    replay.add_argument("--lean-workspace", type=Path, required=True)
    replay.add_argument("--artifact", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    replay.add_argument("--shard-count", type=int, default=1)
    replay.add_argument("--shard-index", type=int, default=0)
    replay.add_argument("--limit", type=int)
    replay.add_argument("--restart-every", type=int, default=128)
    replay.add_argument("--timeout-seconds", type=float, default=300.0)
    replay.add_argument("--memory-limit-gib", type=float, default=24.0)
    replay.add_argument("--progress-every", type=int, default=100)
    replay.add_argument("--proposal-id", action="append")
    summary = commands.add_parser("summarize-replay", help="aggregate replay cost shards")
    summary.add_argument("--artifact", type=Path, action="append", required=True)
    summary.add_argument("--expected-proposals", type=int)
    summary.add_argument("--gate-fraction", type=float, default=0.15)
    summary.add_argument("--bootstrap-samples", type=int, default=10_000)
    summary.add_argument("--bootstrap-seed", type=int, default=42)
    summary.add_argument("--output", type=Path, required=True)
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
        if args.command == "profile-replay":
            report = profile_replay_shard(
                args.manifest,
                args.native_artifact,
                args.artifact,
                lean_workspace=args.lean_workspace,
                source_root=args.source_root,
                shard_count=args.shard_count,
                shard_index=args.shard_index,
                limit=args.limit,
                restart_every=args.restart_every,
                timeout_seconds=args.timeout_seconds,
                memory_limit_bytes=int(args.memory_limit_gib * 1024**3),
                progress_every=args.progress_every,
                proposal_ids=set(args.proposal_id) if args.proposal_id else None,
            )
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
        if args.command == "summarize-replay":
            report = summarize_replay_profiles(
                args.artifact,
                expected_proposals=args.expected_proposals,
                gate_fraction=args.gate_fraction,
                bootstrap_samples=args.bootstrap_samples,
                bootstrap_seed=args.bootstrap_seed,
            )
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
    except (
        AuditError,
        NativeExtractionError,
        ReplayProfileError,
        ProfileSummaryError,
        ReplError,
        ReviewSelectionError,
        OSError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 2
