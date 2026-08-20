"""Existing-artifact-only retention gate for the RL closure workload."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import random
from typing import Any, Iterable

from lean_prefix.projection import required_reusable_fraction
from lean_prefix.rl_workload import build_report as build_admission_report


BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 42
MINIMUM_THROUGHPUT_MULTIPLIER = 1.5
OVERHEAD_FRACTION = 0.02


class RetentionGateError(RuntimeError):
    """Raised when frozen retention evidence is incomplete or inconsistent."""


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
        raise RetentionGateError(f"{path} must contain one JSON object")
    return value


def _quantile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        raise RetentionGateError("cannot take a quantile of no values")
    return sorted_values[int(fraction * (len(sorted_values) - 1))]


def theorem_bootstrap(
    theorem_pairs: list[tuple[float, float]],
    *,
    samples: int = BOOTSTRAP_SAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    if not theorem_pairs:
        raise RetentionGateError("retention gate has no overlapping theorems")
    if samples < 1:
        raise RetentionGateError("bootstrap sample count must be positive")
    rng = random.Random(seed)
    fractions = []
    for _ in range(samples):
        drawn = [theorem_pairs[rng.randrange(len(theorem_pairs))] for _ in theorem_pairs]
        baseline = sum(pair[0] for pair in drawn)
        cached = sum(pair[1] for pair in drawn)
        fractions.append((baseline - cached) / baseline if baseline else 0.0)
    fractions.sort()
    return {
        "samples": samples,
        "seed": seed,
        "low": _quantile(fractions, 0.025),
        "median": _quantile(fractions, 0.5),
        "high": _quantile(fractions, 0.975),
    }


def summarize_retention(
    admission_details: list[dict[str, Any]],
    records: Iterable[dict[str, Any]],
    *,
    conservative_acceleration: float,
) -> dict[str, Any]:
    admitted = {str(item["theorem_name"]): item for item in admission_details}
    theorem_totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "proposals": 0,
            "baseline_cpu_seconds": 0.0,
            "cached_cpu_seconds": 0.0,
            "automatic_hits": 0,
            "verdict_disagreements": 0,
        }
    )
    events: Counter[str] = Counter()
    for record in records:
        theorem_name = str(record["theorem_name"])
        if theorem_name not in admitted:
            continue
        baseline = record.get("baseline") or {}
        cached = record.get("cached") or {}
        baseline_cpu = baseline.get("cpu_seconds")
        cached_cpu = cached.get("cpu_seconds")
        if not isinstance(baseline_cpu, (int, float)) or not isinstance(
            cached_cpu, (int, float)
        ):
            raise RetentionGateError(f"missing paired CPU for {theorem_name}")
        total = theorem_totals[theorem_name]
        total["proposals"] += 1
        total["baseline_cpu_seconds"] += float(baseline_cpu)
        total["cached_cpu_seconds"] += float(cached_cpu)
        total["verdict_disagreements"] += int(
            baseline.get("complete") != cached.get("complete")
        )
        record_events = [str(event["event"]) for event in cached.get("events", [])]
        events.update(record_events)
        total["automatic_hits"] += int("hit" in record_events)

    if not theorem_totals:
        raise RetentionGateError("D030 contains no admitted theorem overlap")
    for theorem_name, total in theorem_totals.items():
        if total["proposals"] != 32:
            raise RetentionGateError(
                f"{theorem_name} has {total['proposals']} D030 proposals, expected 32"
            )

    theorem_rows = []
    for theorem_name in sorted(theorem_totals):
        total = theorem_totals[theorem_name]
        baseline = float(total["baseline_cpu_seconds"])
        cached = float(total["cached_cpu_seconds"])
        detail = admitted[theorem_name]
        theorem_rows.append(
            {
                "theorem_name": theorem_name,
                **total,
                "paired_cpu_saved_seconds": baseline - cached,
                "paired_cpu_saved_fraction": (baseline - cached) / baseline,
                "d019_baseline_cpu_seconds": detail["baseline_cpu_seconds"],
                "d019_conservative_reusable_cpu_seconds": detail[
                    "conservative_reusable_cpu_seconds"
                ],
                "d019_conservative_reusable_cpu_fraction": detail[
                    "conservative_reusable_cpu_fraction"
                ],
            }
        )

    baseline_cpu = sum(row["baseline_cpu_seconds"] for row in theorem_rows)
    cached_cpu = sum(row["cached_cpu_seconds"] for row in theorem_rows)
    saved_cpu = baseline_cpu - cached_cpu
    saved_fraction = saved_cpu / baseline_cpu
    d019_baseline = sum(row["d019_baseline_cpu_seconds"] for row in theorem_rows)
    d019_upper = sum(
        row["d019_conservative_reusable_cpu_seconds"] for row in theorem_rows
    )
    required_fraction = required_reusable_fraction(
        MINIMUM_THROUGHPUT_MULTIPLIER,
        conservative_acceleration,
        OVERHEAD_FRACTION,
    )
    bootstrap = theorem_bootstrap(
        [(row["baseline_cpu_seconds"], row["cached_cpu_seconds"]) for row in theorem_rows]
    )
    gate_passed = bootstrap["high"] >= required_fraction
    return {
        "overlap": {
            "theorems": len(theorem_rows),
            "proposals": sum(int(row["proposals"]) for row in theorem_rows),
            "baseline_cpu_seconds": baseline_cpu,
            "cached_cpu_seconds": cached_cpu,
            "paired_cpu_saved_seconds": saved_cpu,
            "paired_cpu_saved_fraction": saved_fraction,
            "cpu_equivalent_throughput_multiplier": baseline_cpu / cached_cpu,
            "automatic_hits": sum(int(row["automatic_hits"]) for row in theorem_rows),
            "verdict_disagreements": sum(
                int(row["verdict_disagreements"]) for row in theorem_rows
            ),
            "event_counts": dict(sorted(events.items())),
            "positive_saving_theorems": sum(
                row["paired_cpu_saved_seconds"] > 0 for row in theorem_rows
            ),
            "theorem_bootstrap_95_percent": bootstrap,
            "per_theorem": theorem_rows,
        },
        "admission_upper_bound_on_overlap": {
            "d019_baseline_cpu_seconds": d019_baseline,
            "d019_conservative_reusable_cpu_seconds": d019_upper,
            "d019_conservative_reusable_cpu_fraction": d019_upper / d019_baseline,
            "cross_run_saved_seconds_over_upper_bound": saved_cpu / d019_upper,
            "warning": (
                "The ratio compares separate D019 and D030 executions and is diagnostic; "
                "the paired D030 saved fraction is the authoritative retention evidence."
            ),
        },
        "gate": {
            "minimum_throughput_multiplier": MINIMUM_THROUGHPUT_MULTIPLIER,
            "required_realized_reusable_cpu_fraction": required_fraction,
            "observed_paired_cpu_saved_fraction": saved_fraction,
            "bootstrap_high_fraction": bootstrap["high"],
            "passes": gate_passed,
            "decision": (
                "theory_gate_passed"
                if gate_passed
                else "stop_no_new_c1_lean_or_cluster_compute"
            ),
        },
    }


def build_report(
    admission_opportunity_path: Path,
    probe_path: Path,
    prevalence_path: Path,
    *,
    verify_hashes: bool = True,
) -> dict[str, Any]:
    prevalence = _load(prevalence_path)
    if prevalence.get("analysis") != "closing-certificate-prevalence-summary-v1":
        raise RetentionGateError("unexpected D030 prevalence report identity")
    admission = build_admission_report(
        admission_opportunity_path,
        probe_path,
        verify_hashes=verify_hashes,
    )
    artifact_hashes = prevalence["inputs"]["artifact_sha256"]
    records = []
    for path_text in sorted(artifact_hashes):
        path = Path(path_text)
        if verify_hashes and _sha256(path) != artifact_hashes[path_text]:
            raise RetentionGateError(f"D030 artifact checksum mismatch: {path}")
        with gzip.open(path, mode="rt", encoding="utf-8") as handle:
            records.extend(json.loads(line) for line in handle)
    accelerations = sorted(
        float(item["generated_to_applied_plus_check_ratio"])
        for item in _load(probe_path)["benchmarks"]
    )
    report = summarize_retention(
        admission["admitted"]["theorems_detail"],
        records,
        conservative_acceleration=accelerations[0],
    )
    return {
        "analysis": "existing-artifact-rl-retention-gate-v1",
        "evidence_label": "Observed",
        "status": "complete-theory-gate-failed",
        "warning": "No new Lean, REPL, or cluster execution was performed.",
        "configuration": {
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "minimum_throughput_multiplier": MINIMUM_THROUGHPUT_MULTIPLIER,
            "overhead_fraction": OVERHEAD_FRACTION,
            "conservative_application_acceleration": accelerations[0],
        },
        "inputs": {
            "admission_opportunity": {
                "path": str(admission_opportunity_path),
                "sha256": _sha256(admission_opportunity_path),
            },
            "certificate_probe": {
                "path": str(probe_path),
                "sha256": _sha256(probe_path),
            },
            "d030_prevalence": {
                "path": str(prevalence_path),
                "sha256": _sha256(prevalence_path),
            },
            "d019_and_d030_artifact_hashes_verified": verify_hashes,
        },
        **report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--admission-opportunity",
        type=Path,
        default=Path("reports/c0_opportunity_decomposition.json"),
    )
    parser.add_argument(
        "--probe", type=Path, default=Path("reports/c0_certificate_probe.json")
    )
    parser.add_argument(
        "--prevalence",
        type=Path,
        default=Path("reports/c0_certificate_prevalence_d030.json"),
    )
    parser.add_argument("--skip-hash-verification", action="store_true")
    args = parser.parse_args()
    report = build_report(
        args.admission_opportunity,
        args.probe,
        args.prevalence,
        verify_hashes=not args.skip_hash_verification,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
