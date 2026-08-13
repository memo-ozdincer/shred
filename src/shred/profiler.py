"""One-command workload profiler built on SHRED's conservative measurements."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from lean_prefix.analysis import analyze_exact
from lean_prefix.audit import audit_manifest
from lean_prefix.native import extract_and_analyze
from lean_prefix.profile import profile_replay_shard
from lean_prefix.profile_summary import summarize_replay_profiles


class ShredProfileError(RuntimeError):
    """Raised when a workload profile cannot be produced safely."""


@dataclass(frozen=True)
class ProfileConfig:
    """Inputs and resource limits for a SHRED workload profile."""

    manifest: Path
    lean_workspace: Path
    output_dir: Path
    source_root: Path | None = None
    native_artifact: Path | None = None
    extractor: Path = Path("lean/LeanPrefix/Extract.lean")
    repl_executable: Path | None = None
    limit: int | None = 256
    gate_fraction: float = 0.15
    timeout_seconds: float = 300.0
    memory_limit_gib: float = 48.0
    restart_every: int = 128
    bootstrap_samples: int = 10_000
    bootstrap_seed: int = 42
    force: bool = False


@dataclass(frozen=True)
class ProfileResult:
    """A completed profile and the path containing its machine-readable report."""

    report: dict[str, Any]
    report_path: Path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def recommend_profile(
    summary: dict[str, Any], *, gate_fraction: float, screening: bool
) -> dict[str, Any]:
    """Turn a conservative replay summary into an explicit deployment decision."""
    fraction = summary.get("cpu_seconds", {}).get(
        "opportunity_fraction_of_full_verification"
    )
    if summary.get("status") != "complete" or not isinstance(fraction, (int, float)):
        return {
            "decision": "inconclusive",
            "reason": "profiling did not complete with fully attributable measurements",
            "next_step": "inspect fallbacks, timeouts, errors, and verdict disagreements",
        }
    if screening:
        return {
            "decision": "screening_only",
            "reason": (
                f"the sampled cost-weighted exact-prefix opportunity is {fraction:.3%}; "
                "a sample is not release evidence"
            ),
            "passes_gate_on_sample": fraction >= gate_fraction,
            "next_step": (
                "run with --full on a representative immutable workload before deployment"
            ),
        }
    if fraction >= gate_fraction:
        return {
            "decision": "prefix_reuse_candidate",
            "reason": (
                f"cost-weighted exact-prefix opportunity {fraction:.3%} meets the "
                f"registered {gate_fraction:.3%} gate"
            ),
            "next_step": "benchmark the exact executor against warm independent verification",
        }
    return {
        "decision": "do_not_deploy_exact_prefix_reuse",
        "reason": (
            f"cost-weighted exact-prefix opportunity {fraction:.3%} is below the "
            f"registered {gate_fraction:.3%} gate"
        ),
        "next_step": "profile expensive closing-tactic tails before considering certificates",
    }


def profile_workload(config: ProfileConfig) -> ProfileResult:
    """Run SHRED's auditable profiling pipeline and write a compact decision report.

    The default is a 256-proposal screening run. Set ``limit=None`` only for a
    representative full-workload measurement. Existing final reports are never
    overwritten unless ``force`` is set.
    """
    if config.limit is not None and config.limit < 1:
        raise ShredProfileError("limit must be positive or None")
    if not 0 < config.gate_fraction <= 1:
        raise ShredProfileError("gate fraction must be in (0, 1]")
    if config.memory_limit_gib <= 0:
        raise ShredProfileError("memory limit must be positive")

    output_dir = config.output_dir.resolve()
    reports_dir = output_dir / "reports"
    artifacts_dir = output_dir / "artifacts"
    final_path = output_dir / "profile.json"
    if final_path.exists() and not config.force:
        raise ShredProfileError(
            f"refusing to overwrite completed profile {final_path}; pass force=True"
        )
    reports_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    audit = audit_manifest(config.manifest, config.source_root).to_dict()
    exact = analyze_exact(config.manifest, config.source_root)
    _write_json(reports_dir / "audit.json", audit)
    _write_json(reports_dir / "exact.json", exact)

    native_artifact = config.native_artifact
    if native_artifact is None:
        if not config.extractor.is_file():
            raise ShredProfileError(
                f"Lean-native extractor not found: {config.extractor}"
            )
        native_artifact = artifacts_dir / "native_units.jsonl.gz"
        native_report = extract_and_analyze(
            config.manifest,
            lean_workspace=config.lean_workspace,
            extractor_path=config.extractor,
            artifact_path=native_artifact,
            source_root=config.source_root,
            limit=config.limit,
        )
        _write_json(reports_dir / "native.json", native_report)
    elif not native_artifact.is_file():
        raise ShredProfileError(f"native artifact not found: {native_artifact}")

    replay_artifact = artifacts_dir / "replay.jsonl.gz"
    replay_report = profile_replay_shard(
        config.manifest,
        native_artifact,
        replay_artifact,
        lean_workspace=config.lean_workspace,
        source_root=config.source_root,
        limit=config.limit,
        restart_every=config.restart_every,
        timeout_seconds=config.timeout_seconds,
        memory_limit_bytes=int(config.memory_limit_gib * 1024**3),
        repl_executable=config.repl_executable,
    )
    _write_json(reports_dir / "replay.json", replay_report)

    expected = exact["proposals"]
    if config.limit is not None:
        expected = min(expected, config.limit)
    summary = summarize_replay_profiles(
        [replay_artifact],
        expected_proposals=expected,
        gate_fraction=config.gate_fraction,
        bootstrap_samples=config.bootstrap_samples,
        bootstrap_seed=config.bootstrap_seed,
    )
    _write_json(reports_dir / "prefix-opportunity.json", summary)

    report = {
        "schema_version": 1,
        "tool": "shred",
        "scope": "screening_sample" if config.limit is not None else "full_workload",
        "profiled_proposals": expected,
        "workload_proposals": exact["proposals"],
        "recommendation": recommend_profile(
            summary,
            gate_fraction=config.gate_fraction,
            screening=config.limit is not None,
        ),
        "metrics": {
            "exact_duplicate_share": exact["duplicate_proposal_share"],
            "prefix_opportunity_fraction": summary.get("cpu_seconds", {}).get(
                "opportunity_fraction_of_full_verification"
            ),
            "gate_fraction": config.gate_fraction,
        },
        "artifacts": {
            "native_units": {
                "path": str(native_artifact.resolve()),
                "sha256": _sha256(native_artifact),
            },
            "replay": {
                "path": str(replay_artifact),
                "sha256": _sha256(replay_artifact),
            },
        },
        "reports": {
            "audit": str((reports_dir / "audit.json").resolve()),
            "exact": str((reports_dir / "exact.json").resolve()),
            "replay": str((reports_dir / "replay.json").resolve()),
            "prefix_opportunity": str(
                (reports_dir / "prefix-opportunity.json").resolve()
            ),
        },
    }
    _write_json(final_path, report)
    return ProfileResult(report=report, report_path=final_path)
