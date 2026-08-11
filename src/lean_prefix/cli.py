from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import sys

from lean_prefix.audit import AuditError, audit_manifest
from lean_prefix.analysis import analyze_exact
from lean_prefix.certificate_probe import (
    CertificateProbeError,
    summarize_certificate_probe,
)
from lean_prefix.certificate_prevalence import (
    CertificatePrevalenceError,
    prepare_certificate_prevalence_inputs,
    run_certificate_prevalence_theorem,
    select_certificate_prevalence_theorems,
    summarize_certificate_prevalence,
)
from lean_prefix.native import NativeExtractionError, extract_and_analyze
from lean_prefix.opportunity_summary import (
    OpportunitySummaryError,
    summarize_alternative_opportunities,
)
from lean_prefix.profile import ReplayProfileError, profile_replay_shard
from lean_prefix.profile_summary import ProfileSummaryError, summarize_replay_profiles
from lean_prefix.repl import ReplError
from lean_prefix.review import ReviewSelectionError, select_review_sample
from lean_prefix.state_census import (
    StateCensusError,
    capture_visible_states,
    select_edge_opportunity_theorems,
    summarize_visible_state_census,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shred")
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
    replay.add_argument("--memory-limit-gib", type=float, default=48.0)
    replay.add_argument("--repl-executable", type=Path)
    replay.add_argument("--progress-every", type=int, default=100)
    replay.add_argument("--proposal-id", action="append")
    summary = commands.add_parser("summarize-replay", help="aggregate replay cost shards")
    summary.add_argument("--artifact", type=Path, action="append", required=True)
    summary.add_argument("--expected-proposals", type=int)
    summary.add_argument("--gate-fraction", type=float, default=0.15)
    summary.add_argument("--bootstrap-samples", type=int, default=10_000)
    summary.add_argument("--bootstrap-seed", type=int, default=42)
    summary.add_argument("--output", type=Path, required=True)
    opportunities = commands.add_parser(
        "summarize-opportunities",
        help="diagnose broader reuse and tail opportunities without weakening the gate",
    )
    opportunities.add_argument("--artifact", type=Path, action="append", required=True)
    opportunities.add_argument("--native-artifact", type=Path, required=True)
    opportunities.add_argument("--expected-proposals", type=int)
    opportunities.add_argument("--gate-fraction", type=float, default=0.15)
    opportunities.add_argument("--bootstrap-samples", type=int, default=10_000)
    opportunities.add_argument("--bootstrap-seed", type=int, default=42)
    opportunities.add_argument("--output", type=Path, required=True)
    state_select = commands.add_parser(
        "select-state-census", help="select high-opportunity theorems for state diagnostics"
    )
    state_select.add_argument("--artifact", type=Path, action="append", required=True)
    state_select.add_argument("--limit", type=int, default=10)
    state_select.add_argument("--output", type=Path, required=True)
    state_capture = commands.add_parser(
        "capture-state-census", help="capture authentic visible pre-tactic goals"
    )
    state_capture.add_argument("--manifest", type=Path, required=True)
    state_capture.add_argument("--source-root", type=Path)
    state_capture.add_argument("--native-artifact", type=Path, required=True)
    state_capture.add_argument("--lean-workspace", type=Path, required=True)
    state_capture.add_argument("--theorem", required=True)
    state_capture.add_argument("--artifact", type=Path, required=True)
    state_capture.add_argument("--output", type=Path, required=True)
    state_capture.add_argument("--timeout-seconds", type=float, default=300.0)
    state_capture.add_argument("--memory-limit-gib", type=float, default=48.0)
    state_capture.add_argument("--repl-executable", type=Path)
    state_summary = commands.add_parser(
        "summarize-state-census", help="score visible-state reconvergence diagnostics"
    )
    state_summary.add_argument("--state-artifact", type=Path, action="append", required=True)
    state_summary.add_argument("--state-report", type=Path, action="append")
    state_summary.add_argument("--replay-artifact", type=Path, action="append", required=True)
    state_summary.add_argument("--output", type=Path, required=True)
    certificate_summary = commands.add_parser(
        "summarize-certificate-probe",
        help="summarize the registered closing-certificate feasibility profile",
    )
    certificate_summary.add_argument("--profiler-log", type=Path, required=True)
    certificate_summary.add_argument("--output", type=Path, required=True)
    certificate_select = commands.add_parser(
        "select-certificate-prevalence",
        help="freeze representative and enriched certificate theorem strata",
    )
    certificate_select.add_argument("--replay-artifact", type=Path, action="append", required=True)
    certificate_select.add_argument("--representative-count", type=int, default=128)
    certificate_select.add_argument("--enriched-count", type=int, default=32)
    certificate_select.add_argument("--output", type=Path, required=True)
    certificate_prepare = commands.add_parser(
        "prepare-certificate-prevalence",
        help="materialize the selected read-only proposal inputs",
    )
    certificate_prepare.add_argument("--manifest", type=Path, required=True)
    certificate_prepare.add_argument("--source-root", type=Path)
    certificate_prepare.add_argument("--native-artifact", type=Path, required=True)
    certificate_prepare.add_argument("--selection", type=Path, required=True)
    certificate_prepare.add_argument("--artifact", type=Path, required=True)
    certificate_prepare.add_argument("--output", type=Path, required=True)
    certificate_run = commands.add_parser(
        "run-certificate-prevalence-theorem",
        help="run paired original/cached verification for one frozen theorem",
    )
    certificate_run.add_argument("--input-artifact", type=Path, required=True)
    certificate_run.add_argument("--theorem", required=True)
    certificate_run.add_argument("--lean-workspace", type=Path, required=True)
    certificate_run.add_argument("--artifact", type=Path, required=True)
    certificate_run.add_argument("--output", type=Path, required=True)
    certificate_run.add_argument("--timeout-seconds", type=float, default=300.0)
    certificate_run.add_argument("--memory-limit-gib", type=float, default=48.0)
    certificate_run.add_argument("--repl-executable", type=Path)
    certificate_consolidate = commands.add_parser(
        "summarize-certificate-prevalence",
        help="validate and aggregate paired certificate theorem runs",
    )
    certificate_consolidate.add_argument("--artifact", type=Path, action="append", required=True)
    certificate_consolidate.add_argument("--report", type=Path, action="append", required=True)
    certificate_consolidate.add_argument("--selection", type=Path)
    certificate_consolidate.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(raw_argv)
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
                repl_executable=args.repl_executable,
                progress_every=args.progress_every,
                proposal_ids=set(args.proposal_id) if args.proposal_id else None,
            )
            report["command"] = shlex.join(["lean-prefix", *raw_argv])
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
            report["command"] = shlex.join(["lean-prefix", *raw_argv])
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
        if args.command == "summarize-opportunities":
            report = summarize_alternative_opportunities(
                args.artifact,
                args.native_artifact,
                expected_proposals=args.expected_proposals,
                gate_fraction=args.gate_fraction,
                bootstrap_samples=args.bootstrap_samples,
                bootstrap_seed=args.bootstrap_seed,
                project_root=Path.cwd(),
            )
            report["command"] = shlex.join(["lean-prefix", *raw_argv])
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
        if args.command == "select-state-census":
            report = select_edge_opportunity_theorems(
                args.artifact, limit=args.limit, project_root=Path.cwd()
            )
            report["command"] = shlex.join(["lean-prefix", *raw_argv])
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
        if args.command == "capture-state-census":
            report = capture_visible_states(
                args.manifest,
                args.native_artifact,
                args.artifact,
                theorem_name=args.theorem,
                lean_workspace=args.lean_workspace,
                source_root=args.source_root,
                timeout_seconds=args.timeout_seconds,
                memory_limit_bytes=int(args.memory_limit_gib * 1024**3),
                repl_executable=args.repl_executable,
            )
            report["command"] = shlex.join(["lean-prefix", *raw_argv])
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
        if args.command == "summarize-state-census":
            report = summarize_visible_state_census(
                args.state_artifact, args.replay_artifact, args.state_report
            )
            report["command"] = shlex.join(["lean-prefix", *raw_argv])
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
        if args.command == "summarize-certificate-probe":
            report = summarize_certificate_probe(
                args.profiler_log, project_root=Path.cwd()
            )
            report["command"] = shlex.join(["lean-prefix", *raw_argv])
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
        if args.command == "select-certificate-prevalence":
            report = select_certificate_prevalence_theorems(
                args.replay_artifact,
                representative_count=args.representative_count,
                enriched_count=args.enriched_count,
                project_root=Path.cwd(),
            )
            report["command"] = shlex.join(["lean-prefix", *raw_argv])
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
        if args.command == "prepare-certificate-prevalence":
            report = prepare_certificate_prevalence_inputs(
                args.manifest,
                args.native_artifact,
                args.selection,
                args.artifact,
                source_root=args.source_root,
            )
            report["command"] = shlex.join(["lean-prefix", *raw_argv])
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
        if args.command == "run-certificate-prevalence-theorem":
            report = run_certificate_prevalence_theorem(
                args.input_artifact,
                args.artifact,
                theorem_name=args.theorem,
                lean_workspace=args.lean_workspace,
                timeout_seconds=args.timeout_seconds,
                memory_limit_bytes=int(args.memory_limit_gib * 1024**3),
                repl_executable=args.repl_executable,
            )
            report["command"] = shlex.join(["lean-prefix", *raw_argv])
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
        if args.command == "summarize-certificate-prevalence":
            report = summarize_certificate_prevalence(
                args.artifact, args.report, args.selection
            )
            report["command"] = shlex.join(["lean-prefix", *raw_argv])
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
        OpportunitySummaryError,
        CertificateProbeError,
        CertificatePrevalenceError,
        ReplError,
        ReviewSelectionError,
        StateCensusError,
        OSError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 2
