"""Diagnostic opportunity decomposition after the registered prefix gate.

This module never upgrades a failed verifier gate into a performance claim.
Broader groupings are reported only as diagnostics or unsafe upper bounds.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Iterator

from lean_prefix.profile import _git_state
from lean_prefix.profile_summary import _bootstrap_ratio


class OpportunitySummaryError(RuntimeError):
    """Raised when alternative-opportunity inputs are inconsistent."""


def _records(paths: Iterable[Path]) -> Iterator[dict[str, Any]]:
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else Path.open
        mode = "rt" if path.suffix == ".gz" else "r"
        with opener(path, mode=mode, encoding="utf-8") as stream:
            for line in stream:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise OpportunitySummaryError(f"non-object record in {path}")
                yield value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _oracle(groups: dict[Any, list[float]], denominator: float) -> dict[str, Any]:
    independent = sum(sum(values) for values in groups.values())
    unique_mean = sum(sum(values) / len(values) for values in groups.values())
    unique_worst = sum(max(values) for values in groups.values())
    mean_saved = independent - unique_mean
    worst_saved = independent - unique_worst
    return {
        "groups": len(groups),
        "occurrences": sum(len(values) for values in groups.values()),
        "repeated_occurrences": sum(len(values) - 1 for values in groups.values()),
        "independent_cpu_seconds": independent,
        "saved_cpu_seconds_mean_representative": mean_saved,
        "saved_cpu_seconds_worst_observed_representative": worst_saved,
        "fraction_of_full_cpu_mean_representative": (
            mean_saved / denominator if denominator else None
        ),
        "fraction_of_full_cpu_worst_observed_representative": (
            worst_saved / denominator if denominator else None
        ),
    }


def _outcome(full: dict[str, Any]) -> str:
    if full.get("timed_out") is True:
        return "timeout"
    if "complete" in full:
        return "accept" if full["complete"] else "reject"
    return "error"


def _concentration(values: list[float], fraction: float) -> dict[str, Any]:
    if not values:
        return {"count": 0, "share": None, "threshold_seconds": None}
    ordered = sorted(values, reverse=True)
    count = max(1, math.ceil(len(ordered) * fraction))
    return {
        "count": count,
        "share": sum(ordered[:count]) / sum(ordered),
        "threshold_seconds": ordered[count - 1],
    }


def summarize_alternative_opportunities(
    artifact_paths: list[Path],
    native_artifact_path: Path,
    *,
    expected_proposals: int | None = None,
    gate_fraction: float = 0.15,
    bootstrap_samples: int = 10_000,
    bootstrap_seed: int = 42,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Decompose measured costs without weakening the registered gate."""
    if not artifact_paths:
        raise OpportunitySummaryError("at least one replay artifact is required")
    if not 0 <= gate_fraction <= 1:
        raise OpportunitySummaryError("gate fraction must be in [0, 1]")
    if bootstrap_samples < 0:
        raise OpportunitySummaryError("bootstrap sample count must be non-negative")

    proof_hashes: dict[str, str] = {}
    for record in _records([native_artifact_path]):
        proposal_id = str(record["proposal_id"])
        if proposal_id in proof_hashes:
            raise OpportunitySummaryError(f"duplicate native proposal: {proposal_id}")
        proof_hashes[proposal_id] = str(record["proof_sha256"])

    seen: set[str] = set()
    full_cpu = 0.0
    full_cpu_values: list[float] = []
    full_wall_values: list[float] = []
    timeout_cpu = 0.0
    cpu_covered = 0
    verdict_disagreements = profile_disagreements = 0
    full_failures = profile_failures = 0
    outcomes: Counter[str] = Counter()
    prefix_groups: dict[str, list[float]] = defaultdict(list)
    prefix_theorem: dict[str, str] = {}
    edge_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    kind_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    proof_groups: dict[tuple[str, str], list[tuple[str, float | None]]] = defaultdict(list)

    for record in _records(artifact_paths):
        proposal_id = str(record["proposal_id"])
        if proposal_id in seen:
            raise OpportunitySummaryError(f"duplicate replay proposal: {proposal_id}")
        seen.add(proposal_id)
        if proposal_id not in proof_hashes:
            raise OpportunitySummaryError(f"missing native proposal: {proposal_id}")
        theorem = str(record["theorem_name"])
        full = record.get("full") or {}
        outcome = _outcome(full)
        outcomes[outcome] += 1
        if full.get("verdict_match") is False:
            verdict_disagreements += 1
        if "complete" not in full:
            full_failures += int(outcome != "timeout")
        cpu = full.get("cpu_seconds")
        numeric_cpu = float(cpu) if isinstance(cpu, (int, float)) else None
        if numeric_cpu is not None:
            full_cpu += numeric_cpu
            full_cpu_values.append(numeric_cpu)
            cpu_covered += 1
            if outcome == "timeout":
                timeout_cpu += numeric_cpu
        wall = full.get("wall_seconds")
        if isinstance(wall, (int, float)):
            full_wall_values.append(float(wall))
        proof_groups[(theorem, proof_hashes[proposal_id])].append((outcome, numeric_cpu))

        profile = record.get("profile", record.get("sequential"))
        if record.get("replay_eligible"):
            if not isinstance(profile, dict) or "complete" not in profile:
                profile_failures += 1
            elif profile.get("verdict_match") is False:
                profile_disagreements += 1
        for step in record.get("steps", []):
            step_cpu = step.get("cpu_seconds")
            if step.get("reachability") != "reached" or not isinstance(
                step_cpu, (int, float)
            ):
                continue
            value = float(step_cpu)
            prefix = str(step["prefix_sha256"])
            prior_theorem = prefix_theorem.setdefault(prefix, theorem)
            if prior_theorem != theorem:
                raise OpportunitySummaryError(f"prefix hash crosses theorems: {prefix}")
            prefix_groups[prefix].append(value)
            edge_groups[(theorem, str(step["edge_sha256"]))].append(value)
            kind_groups[(theorem, str(step["syntax_kind"]))].append(value)

    if expected_proposals is not None and len(seen) != expected_proposals:
        raise OpportunitySummaryError(
            f"expected {expected_proposals} proposals, found {len(seen)}"
        )

    completed_duplicate_groups: dict[tuple[str, str], list[float]] = {}
    excluded_duplicate_groups = 0
    for key, values in proof_groups.items():
        if len(values) < 2:
            continue
        group_outcomes = {outcome for outcome, _ in values}
        cpus = [cpu for _, cpu in values]
        if (
            len(group_outcomes) == 1
            and next(iter(group_outcomes)) in {"accept", "reject"}
            and all(cpu is not None for cpu in cpus)
        ):
            completed_duplicate_groups[key] = [float(cpu) for cpu in cpus if cpu is not None]
        else:
            excluded_duplicate_groups += 1

    prefix = _oracle(prefix_groups, full_cpu)
    exact_proof = _oracle(completed_duplicate_groups, full_cpu)
    edge = _oracle(edge_groups, full_cpu)
    kind = _oracle(kind_groups, full_cpu)

    saved_by_theorem: dict[str, float] = defaultdict(float)
    total_by_theorem: dict[str, float] = defaultdict(float)
    for (theorem, _), values in proof_groups.items():
        total_by_theorem[theorem] += sum(cpu for _, cpu in values if cpu is not None)
    for prefix_hash, values in prefix_groups.items():
        saved_by_theorem[prefix_theorem[prefix_hash]] += sum(values) - sum(values) / len(values)
    theorem_pairs = [
        (saved_by_theorem[theorem], total)
        for theorem, total in total_by_theorem.items()
    ]

    claim_valid = (
        verdict_disagreements == 0
        and profile_disagreements == 0
        and full_failures == 0
        and profile_failures == 0
        and cpu_covered == len(seen)
    )
    primary_fraction = prefix["fraction_of_full_cpu_mean_representative"]
    return {
        "analysis": "post-gate-opportunity-decomposition-v1",
        "status": "claim-valid" if claim_valid else "diagnostic-only",
        "inputs": {
            "replay_artifacts": {str(path): _sha256(path) for path in artifact_paths},
            "native_artifact": {
                "path": str(native_artifact_path),
                "sha256": _sha256(native_artifact_path),
            },
            "expected_proposals": expected_proposals,
        },
        "revisions": {
            "project_git": _git_state((project_root or Path.cwd()).resolve()),
        },
        "counts": {
            "proposals": len(seen),
            "cpu_covered_proposals": cpu_covered,
            "outcomes": dict(sorted(outcomes.items())),
            "verdict_disagreements": verdict_disagreements,
            "profile_verdict_disagreements": profile_disagreements,
            "full_process_failures": full_failures,
            "profile_failures": profile_failures,
        },
        "baseline": {
            "full_cpu_seconds_with_telemetry": full_cpu,
            "warning": (
                "missing process-death CPU makes every fraction an upper estimate"
                if cpu_covered != len(seen)
                else None
            ),
        },
        "registered_exact_rooted_prefix": {
            **prefix,
            "gate_fraction": gate_fraction,
            "claim_valid": claim_valid,
            "gate_passed": bool(
                claim_valid and primary_fraction is not None and primary_fraction >= gate_fraction
            ),
            "theorem_bootstrap_95_percent": _bootstrap_ratio(
                theorem_pairs, samples=bootstrap_samples, seed=bootstrap_seed
            ),
        },
        "exact_complete_proof_memoization": {
            **exact_proof,
            "scope": "only duplicate groups with complete, verdict-consistent observations",
            "excluded_mixed_timeout_error_groups": excluded_duplicate_groups,
        },
        "unsafe_upper_bounds": {
            "exact_tactic_edge_within_theorem_ignoring_state": edge,
            "tactic_kind_within_theorem_ignoring_source_and_state": kind,
            "warning": (
                "These groupings are not executable cache keys and cannot support a speed claim."
            ),
        },
        "tail": {
            "timeout_cpu_seconds": timeout_cpu,
            "timeout_cpu_fraction": timeout_cpu / full_cpu if full_cpu else None,
            "top_0_1_percent_cpu": _concentration(full_cpu_values, 0.001),
            "top_1_percent_cpu": _concentration(full_cpu_values, 0.01),
            "top_5_percent_cpu": _concentration(full_cpu_values, 0.05),
            "top_1_percent_wall": _concentration(full_wall_values, 0.01),
        },
    }
