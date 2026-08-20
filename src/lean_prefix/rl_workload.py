"""Freeze the discovery-only admission cohort for the held-out RL benchmark."""

from __future__ import annotations

import argparse
from collections import defaultdict
import copy
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from lean_prefix.corpus import iter_proposals
from lean_prefix.projection import projected_speedup, required_reusable_fraction


ALLOWED_FINAL_SYNTAX = frozenset(
    {
        "nlinarith",
        "linarith",
        "Mathlib.Tactic.Positivity.positivity",
    }
)
CONTROL_SEED = "shred-rl-arithmetic-closure-control-v1"
EXPECTED_PROPOSALS_PER_THEOREM = 32
MINIMUM_BASELINE_CPU_SECONDS = 4.0
MINIMUM_REPEATED_OCCURRENCES = 4
MINIMUM_REUSABLE_CPU_FRACTION = 0.40
CONTROL_THEOREMS = 128
PROJECTION_OVERHEAD_FRACTION = 0.02


class RlWorkloadError(RuntimeError):
    """Raised when frozen discovery evidence cannot define the RL workload."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RlWorkloadError(f"{path} must contain one JSON object")
    return value


def _records(paths: Iterable[Path]) -> Iterator[dict[str, Any]]:
    for path in paths:
        with gzip.open(path, mode="rt", encoding="utf-8") as handle:
            for line in handle:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise RlWorkloadError(f"non-object replay record in {path}")
                yield value


def _control_rank(theorem_name: str) -> str:
    value = f"{CONTROL_SEED}\0{theorem_name}".encode()
    return hashlib.sha256(value).hexdigest()


def _theorem_digest(theorem_names: list[str]) -> str:
    payload = "".join(f"{name}\n" for name in theorem_names).encode()
    return hashlib.sha256(payload).hexdigest()


def select_rl_workload(
    replay_paths: list[Path],
    *,
    conservative_acceleration: float,
    verify_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    if verify_hashes is not None:
        actual_paths = {str(path) for path in replay_paths}
        if actual_paths != set(verify_hashes):
            raise RlWorkloadError("replay paths do not match the immutable manifest")
        for path in replay_paths:
            if _sha256(path) != verify_hashes[str(path)]:
                raise RlWorkloadError(f"replay checksum mismatch: {path}")

    theorems: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "proposals": 0,
            "baseline_cpu_seconds": 0.0,
            "missing_cpu": 0,
            "groups": defaultdict(list),
        }
    )
    source_proposals = 0
    for record in _records(replay_paths):
        source_proposals += 1
        theorem_name = str(record["theorem_name"])
        theorem = theorems[theorem_name]
        theorem["proposals"] += 1
        full = record.get("full") or {}
        full_cpu = full.get("cpu_seconds")
        if isinstance(full_cpu, (int, float)):
            theorem["baseline_cpu_seconds"] += float(full_cpu)
        else:
            theorem["missing_cpu"] += 1

        steps = record.get("steps") or []
        if full.get("complete") is not True or not steps:
            continue
        final = max(steps, key=lambda step: int(step["depth"]))
        final_cpu = final.get("cpu_seconds")
        syntax_kind = str(final.get("syntax_kind"))
        if (
            final.get("reachability") == "reached"
            and syntax_kind in ALLOWED_FINAL_SYNTAX
            and isinstance(final_cpu, (int, float))
        ):
            key = (str(final["edge_sha256"]), syntax_kind)
            theorem["groups"][key].append(float(final_cpu))

    cohort: list[dict[str, Any]] = []
    eligible_controls: list[str] = []
    for theorem_name, theorem in theorems.items():
        if theorem["proposals"] != EXPECTED_PROPOSALS_PER_THEOREM:
            raise RlWorkloadError(
                f"{theorem_name} has {theorem['proposals']} proposals, expected 32"
            )
        reusable_cpu = 0.0
        occurrences = 0
        repeated_groups = 0
        syntax_kinds: set[str] = set()
        for (_, syntax_kind), values in theorem["groups"].items():
            if len(values) < 2:
                continue
            reusable_cpu += max(0.0, sum(values) - max(values))
            occurrences += len(values)
            repeated_groups += 1
            syntax_kinds.add(syntax_kind)
        baseline_cpu = float(theorem["baseline_cpu_seconds"])
        reusable_fraction = reusable_cpu / baseline_cpu if baseline_cpu else 0.0
        complete_input = theorem["missing_cpu"] == 0
        admitted = (
            complete_input
            and baseline_cpu >= MINIMUM_BASELINE_CPU_SECONDS
            and occurrences >= MINIMUM_REPEATED_OCCURRENCES
            and reusable_fraction >= MINIMUM_REUSABLE_CPU_FRACTION
        )
        if admitted:
            cohort.append(
                {
                    "theorem_name": theorem_name,
                    "baseline_cpu_seconds": baseline_cpu,
                    "conservative_reusable_cpu_seconds": reusable_cpu,
                    "conservative_reusable_cpu_fraction": reusable_fraction,
                    "repeated_final_edge_groups": repeated_groups,
                    "repeated_final_edge_occurrences": occurrences,
                    "syntax_kinds": sorted(syntax_kinds),
                }
            )
        elif complete_input:
            eligible_controls.append(theorem_name)

    cohort.sort(key=lambda item: item["theorem_name"])
    theorem_names = [str(item["theorem_name"]) for item in cohort]
    controls = sorted(
        eligible_controls, key=lambda name: (_control_rank(name), name)
    )[:CONTROL_THEOREMS]
    baseline_cpu = sum(float(item["baseline_cpu_seconds"]) for item in cohort)
    reusable_cpu = sum(
        float(item["conservative_reusable_cpu_seconds"]) for item in cohort
    )
    reusable_fraction = reusable_cpu / baseline_cpu if baseline_cpu else 0.0
    projection = projected_speedup(
        reusable_fraction,
        conservative_acceleration,
        PROJECTION_OVERHEAD_FRACTION,
    )
    required_for_gate = required_reusable_fraction(
        1.5,
        conservative_acceleration,
        PROJECTION_OVERHEAD_FRACTION,
    )
    return {
        "analysis": "shred-rl-arithmetic-closure-admission-v1",
        "evidence_label": "Observed",
        "status": "held-out-rollout-frozen-paired-evaluation-required",
        "warning": (
            "Admission uses independent C0 telemetry only. The projection is a "
            "hypothesis and cannot become a performance claim until the held-out "
            "C1 rollout passes paired correctness and end-to-end measurement."
        ),
        "admission_rule": {
            "allowed_final_syntax_kinds": sorted(ALLOWED_FINAL_SYNTAX),
            "expected_proposals_per_theorem": EXPECTED_PROPOSALS_PER_THEOREM,
            "minimum_baseline_cpu_seconds": MINIMUM_BASELINE_CPU_SECONDS,
            "minimum_repeated_final_edge_occurrences": MINIMUM_REPEATED_OCCURRENCES,
            "minimum_conservative_reusable_cpu_fraction": MINIMUM_REUSABLE_CPU_FRACTION,
            "reusable_cost_rule": "sum(reached final-edge CPU) - max(reached final-edge CPU)",
        },
        "source": {
            "proposals": source_proposals,
            "theorems": len(theorems),
        },
        "admitted": {
            "theorems": len(cohort),
            "next_rollout_proposals": len(cohort) * EXPECTED_PROPOSALS_PER_THEOREM,
            "baseline_cpu_seconds": baseline_cpu,
            "conservative_reusable_cpu_seconds": reusable_cpu,
            "conservative_reusable_cpu_fraction": reusable_fraction,
            "theorem_names_sha256": _theorem_digest(theorem_names),
            "theorems_detail": cohort,
        },
        "control": {
            "seed": CONTROL_SEED,
            "theorems": len(controls),
            "next_rollout_proposals": len(controls) * EXPECTED_PROPOSALS_PER_THEOREM,
            "theorem_names_sha256": _theorem_digest(sorted(controls)),
            "theorem_names": sorted(controls),
        },
        "projection": {
            "evidence_label": "Hypothesis",
            "interpretation": "upper_sensitivity_assuming_full_signal_retention",
            "conservative_application_acceleration": conservative_acceleration,
            "overhead_fraction": PROJECTION_OVERHEAD_FRACTION,
            **projection,
        },
        "no_compute_theory_gate": {
            "status": "not_yet_passed",
            "minimum_throughput_multiplier": 1.5,
            "required_realized_reusable_cpu_fraction": required_for_gate,
            "required_retention_of_admission_signal": (
                required_for_gate / reusable_fraction if reusable_fraction else None
            ),
            "new_c1_lean_or_cluster_work_authorized": False,
        },
    }


def build_report(
    opportunity_manifest_path: Path,
    probe_path: Path,
    *,
    verify_hashes: bool = True,
    evaluation_manifest_path: Path | None = None,
) -> dict[str, Any]:
    manifest = _load(opportunity_manifest_path)
    probe = _load(probe_path)
    if manifest.get("analysis") != "post-gate-opportunity-decomposition-v1":
        raise RlWorkloadError("unexpected opportunity manifest identity")
    if probe.get("analysis") != "closing-certificate-feasibility-d024-v1":
        raise RlWorkloadError("unexpected certificate probe identity")
    replay_hashes = manifest["inputs"]["replay_artifacts"]
    paths = [Path(path) for path in sorted(replay_hashes)]
    accelerations = sorted(
        float(item["generated_to_applied_plus_check_ratio"])
        for item in probe["benchmarks"]
    )
    report = select_rl_workload(
        paths,
        conservative_acceleration=accelerations[0],
        verify_hashes=replay_hashes if verify_hashes else None,
    )
    report["inputs"] = {
        "opportunity_manifest": {
            "path": str(opportunity_manifest_path),
            "sha256": _sha256(opportunity_manifest_path),
        },
        "certificate_probe": {
            "path": str(probe_path),
            "sha256": _sha256(probe_path),
        },
        "replay_artifacts_verified": verify_hashes,
    }
    if evaluation_manifest_path is not None:
        admitted_names = {
            str(item["theorem_name"])
            for item in report["admitted"]["theorems_detail"]
        }
        control_names = set(report["control"]["theorem_names"])
        evaluation = {
            "admitted": defaultdict(int),
            "control": defaultdict(int),
        }
        seen = {"admitted": set(), "control": set()}
        for proposal in iter_proposals(evaluation_manifest_path):
            name = proposal.theorem_name
            stratum = (
                "admitted"
                if name in admitted_names
                else "control" if name in control_names else None
            )
            if stratum is None:
                continue
            seen[stratum].add(name)
            counts = evaluation[stratum]
            counts["proposals"] += 1
            counts["historical_correct"] += int(proposal.correct)
            counts["historical_timeouts"] += int(bool(proposal.record.get("timed_out")))
            failure = str(proposal.record.get("failure_class"))
            if failure == "proof_parse_failure":
                counts["historical_proof_parse_failures"] += 1
            elif failure == "verifier_exception":
                counts["historical_verifier_exceptions"] += 1
        expected = {
            "admitted": len(admitted_names) * EXPECTED_PROPOSALS_PER_THEOREM,
            "control": len(control_names) * EXPECTED_PROPOSALS_PER_THEOREM,
        }
        for stratum in ("admitted", "control"):
            if evaluation[stratum]["proposals"] != expected[stratum]:
                raise RlWorkloadError(
                    f"evaluation {stratum} has {evaluation[stratum]['proposals']} "
                    f"proposals, expected {expected[stratum]}"
                )
            evaluation[stratum]["theorems"] = len(seen[stratum])
            evaluation[stratum]["historical_correct_fraction"] = (
                evaluation[stratum]["historical_correct"]
                / evaluation[stratum]["proposals"]
            )
        report["evaluation_dataset"] = {
            "evidence_label": "Observed",
            "warning": (
                "Historical source verdicts describe the frozen stream; paired "
                "ordinary Lean replay remains the evaluation authority."
            ),
            "admitted": dict(evaluation["admitted"]),
            "control": dict(evaluation["control"]),
        }
        report["inputs"]["evaluation_manifest"] = {
            "path": str(evaluation_manifest_path),
            "sha256": _sha256(evaluation_manifest_path),
        }
    return report


def summarize_report(report: dict[str, Any]) -> dict[str, Any]:
    """Remove proposal-selection detail while retaining exact selection digests."""
    summary = copy.deepcopy(report)
    summary["analysis"] = f"{report['analysis']}-summary"
    summary["admitted"].pop("theorems_detail", None)
    summary["control"].pop("theorem_names", None)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--opportunity-manifest",
        type=Path,
        default=Path("reports/c0_opportunity_decomposition.json"),
    )
    parser.add_argument(
        "--probe", type=Path, default=Path("reports/c0_certificate_probe.json")
    )
    parser.add_argument(
        "--evaluation-manifest",
        type=Path,
        default=Path("data/c1-rl.manifest.json"),
    )
    parser.add_argument("--skip-hash-verification", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    report = build_report(
        args.opportunity_manifest,
        args.probe,
        verify_hashes=not args.skip_hash_verification,
        evaluation_manifest_path=args.evaluation_manifest,
    )
    if args.summary:
        report = summarize_report(report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
