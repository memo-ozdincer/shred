"""Aggregate cost-profile shards and evaluate the pre-registered gate."""

from __future__ import annotations

from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import random
from typing import Any, Iterable, Iterator


class ProfileSummaryError(RuntimeError):
    """Raised when profile shards are inconsistent or incomplete."""


def _records(paths: Iterable[Path]) -> Iterator[dict[str, Any]]:
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else Path.open
        mode = "rt" if path.suffix == ".gz" else "r"
        with opener(path, mode=mode, encoding="utf-8") as stream:
            for line in stream:
                yield json.loads(line)


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * probability)]


def _bootstrap_ratio(
    theorem_pairs: list[tuple[float, float]], *, samples: int, seed: int
) -> dict[str, float | int | None]:
    usable = [(saved, total) for saved, total in theorem_pairs if total > 0]
    if not usable or samples == 0:
        return {"samples": samples, "seed": seed, "low": None, "high": None}
    generator = random.Random(seed)
    ratios: list[float] = []
    for _ in range(samples):
        saved = total = 0.0
        for _ in range(len(usable)):
            item_saved, item_total = usable[generator.randrange(len(usable))]
            saved += item_saved
            total += item_total
        ratios.append(saved / total if total else 0.0)
    return {
        "samples": samples,
        "seed": seed,
        "low": _quantile(ratios, 0.025),
        "high": _quantile(ratios, 0.975),
    }


def summarize_replay_profiles(
    artifact_paths: list[Path],
    *,
    expected_proposals: int | None = None,
    gate_fraction: float = 0.15,
    bootstrap_samples: int = 10_000,
    bootstrap_seed: int = 42,
) -> dict[str, Any]:
    if not artifact_paths:
        raise ProfileSummaryError("at least one replay artifact is required")
    if not 0 <= gate_fraction <= 1:
        raise ProfileSummaryError("gate fraction must be in [0, 1]")
    if bootstrap_samples < 0:
        raise ProfileSummaryError("bootstrap sample count must be non-negative")

    seen: set[str] = set()
    full_cpu_by_theorem: dict[str, float] = defaultdict(float)
    full_wall_by_theorem: dict[str, float] = defaultdict(float)
    prefix_cpu: dict[str, list[float]] = defaultdict(list)
    prefix_wall: dict[str, list[float]] = defaultdict(list)
    prefix_heartbeats: dict[str, list[float]] = defaultdict(list)
    prefix_theorem: dict[str, str] = {}
    verdict_disagreements = full_failures = sequential_disagreements = sequential_failures = 0
    syntactic_units = reached_units = unreachable_units = completed_tail_units = 0
    invalid_root_units = replayed = 0
    root_unavailable = 0
    replay_eligible = replay_fallback = replay_fallback_units = 0
    missing_full_cpu = missing_step_cpu = 0

    for record in _records(artifact_paths):
        proposal_id = str(record["proposal_id"])
        if proposal_id in seen:
            raise ProfileSummaryError(f"duplicate proposal across shards: {proposal_id}")
        seen.add(proposal_id)
        theorem = str(record["theorem_name"])
        full = record.get("full") or {}
        if full.get("verdict_match") is False:
            verdict_disagreements += 1
        if "complete" not in full:
            full_failures += 1
        if isinstance(full.get("cpu_seconds"), (int, float)):
            full_cpu_by_theorem[theorem] += float(full["cpu_seconds"])
        elif "complete" in full:
            missing_full_cpu += 1
        if isinstance(full.get("wall_seconds"), (int, float)):
            full_wall_by_theorem[theorem] += float(full["wall_seconds"])

        sequential = record.get("sequential")
        native_eligible = bool(record.get("native_eligible"))
        record_replay_eligible = native_eligible and bool(
            record.get("replay_eligible", native_eligible)
        )
        if record_replay_eligible:
            replay_eligible += 1
            if not isinstance(sequential, dict) or "complete" not in sequential:
                sequential_failures += 1
            elif sequential.get("verdict_match") is False:
                sequential_disagreements += 1
            if isinstance(sequential, dict) and sequential.get("root_available") is False:
                root_unavailable += 1
        elif native_eligible:
            replay_fallback += 1
            replay_fallback_units += int(
                record.get("native_unit_count", len(record.get("steps", [])))
            )

        syntactic_units += int(record.get("native_unit_count", len(record.get("steps", []))))
        if not record_replay_eligible:
            continue
        for step in record.get("steps", []):
            reachability = step.get("reachability", "reached")
            if reachability == "unreachable_after_failure":
                unreachable_units += 1
                continue
            if reachability == "unreachable_after_completion":
                completed_tail_units += 1
                continue
            if reachability == "unreachable_invalid_root":
                invalid_root_units += 1
                continue
            if reachability != "reached":
                raise ProfileSummaryError(
                    f"unknown reachability {reachability!r} for proposal {proposal_id}"
                )
            reached_units += 1
            if "wall_seconds" not in step:
                continue
            replayed += 1
            prefix = str(step["prefix_sha256"])
            prior_theorem = prefix_theorem.setdefault(prefix, theorem)
            if prior_theorem != theorem:
                raise ProfileSummaryError(f"prefix hash crosses theorems: {prefix}")
            if isinstance(step.get("cpu_seconds"), (int, float)):
                prefix_cpu[prefix].append(float(step["cpu_seconds"]))
            else:
                missing_step_cpu += 1
            if isinstance(step.get("wall_seconds"), (int, float)):
                prefix_wall[prefix].append(float(step["wall_seconds"]))
            if isinstance(step.get("heartbeats"), (int, float)):
                prefix_heartbeats[prefix].append(float(step["heartbeats"]))

    if expected_proposals is not None and len(seen) != expected_proposals:
        raise ProfileSummaryError(
            f"expected {expected_proposals} proposals, found {len(seen)} across replay shards"
        )
    if verdict_disagreements:
        raise ProfileSummaryError(
            f"refusing cost claim with {verdict_disagreements} verifier disagreements"
        )
    if sequential_disagreements:
        raise ProfileSummaryError(
            f"refusing cost claim with {sequential_disagreements} sequential replay disagreements"
        )

    def costs(groups: dict[str, list[float]]) -> tuple[float, float, float]:
        independent = sum(sum(values) for values in groups.values())
        unique = sum(sum(values) / len(values) for values in groups.values() if values)
        return independent, unique, independent - unique

    independent_cpu, unique_cpu, saved_cpu = costs(prefix_cpu)
    independent_wall, unique_wall, saved_wall = costs(prefix_wall)
    independent_heartbeats, unique_heartbeats, saved_heartbeats = costs(prefix_heartbeats)
    total_full_cpu = sum(full_cpu_by_theorem.values())
    total_full_wall = sum(full_wall_by_theorem.values())

    saved_cpu_by_theorem: dict[str, float] = defaultdict(float)
    for prefix, values in prefix_cpu.items():
        if values:
            saved_cpu_by_theorem[prefix_theorem[prefix]] += sum(values) - sum(values) / len(values)
    theorem_pairs = [
        (saved_cpu_by_theorem[theorem], total)
        for theorem, total in full_cpu_by_theorem.items()
    ]
    per_theorem_fractions = [saved / total for saved, total in theorem_pairs if total > 0]
    opportunity = saved_cpu / total_full_cpu if total_full_cpu else 0.0

    hashes = {}
    for path in artifact_paths:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        hashes[str(path)] = digest.hexdigest()

    return {
        "analysis": "reached-tactic-cost-summary-v1",
        "status": (
            "complete"
            if (
                full_failures == 0
                and sequential_failures == 0
                and replayed == reached_units
                and missing_full_cpu == 0
                and missing_step_cpu == 0
            )
            else "incomplete"
        ),
        "inputs": {"artifacts": hashes, "expected_proposals": expected_proposals},
        "counts": {
            "proposals": len(seen),
            "full_failures": full_failures,
            "verdict_disagreements": verdict_disagreements,
            "sequential_failures": sequential_failures,
            "sequential_verdict_disagreements": sequential_disagreements,
            "native_syntactic_units": syntactic_units,
            "native_reached_units": reached_units,
            "unreachable_after_failure": unreachable_units,
            "unreachable_after_completion": completed_tail_units,
            "unreachable_invalid_root": invalid_root_units,
            "replayed_units": replayed,
            "root_unavailable": root_unavailable,
            "replay_eligible_proposals": replay_eligible,
            "replay_fallback_proposals": replay_fallback,
            "replay_fallback_units": replay_fallback_units,
            "missing_full_cpu": missing_full_cpu,
            "missing_step_cpu": missing_step_cpu,
            "unique_profiled_prefixes": len(prefix_wall),
        },
        "cpu_seconds": {
            "full_independent_verification": total_full_cpu,
            "profiled_reached_units": independent_cpu,
            "unique_prefix_oracle": unique_cpu,
            "reusable_prefix_opportunity": saved_cpu,
            "opportunity_fraction_of_full_verification": opportunity,
        },
        "wall_seconds": {
            "full_independent_verification": total_full_wall,
            "profiled_reached_units": independent_wall,
            "unique_prefix_oracle": unique_wall,
            "reusable_prefix_opportunity": saved_wall,
            "opportunity_fraction_of_full_verification": (
                saved_wall / total_full_wall if total_full_wall else 0.0
            ),
        },
        "heartbeats": {
            "independent_successful_units": independent_heartbeats,
            "unique_prefix_oracle_successful_units": unique_heartbeats,
            "reusable_prefix_opportunity_successful_units": saved_heartbeats,
        },
        "per_theorem_cpu_opportunity_fraction": {
            "median": _quantile(per_theorem_fractions, 0.5),
            "p90": _quantile(per_theorem_fractions, 0.9),
            "p99": _quantile(per_theorem_fractions, 0.99),
            "max": max(per_theorem_fractions, default=None),
        },
        "theorem_bootstrap_95_percent": _bootstrap_ratio(
            theorem_pairs, samples=bootstrap_samples, seed=bootstrap_seed
        ),
        "pre_registered_gate": {
            "threshold": gate_fraction,
            "measured_fraction": opportunity,
            "passes": (
                full_failures == 0
                and sequential_failures == 0
                and replayed == reached_units
                and missing_full_cpu == 0
                and missing_step_cpu == 0
                and opportunity >= gate_fraction
            ),
        },
    }
