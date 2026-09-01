"""Hypothesis-only projections for workloads well suited to certificate reuse."""

from __future__ import annotations

import argparse
import heapq
import hashlib
import json
import math
from pathlib import Path
from typing import Any


DEFAULT_SHARES = (0.25, 0.40, 0.60, 0.80)
DEFAULT_OVERHEAD = 0.02


class ProjectionError(RuntimeError):
    """Raised when a projection input does not match the frozen evidence."""


def _lpt_makespan(jobs: list[float], slots: int) -> float:
    loads = [(0.0, index) for index in range(min(slots, max(1, len(jobs))))]
    heapq.heapify(loads)
    for cost in sorted(jobs, reverse=True):
        load, index = heapq.heappop(loads)
        heapq.heappush(loads, (load + cost, index))
    return max(load for load, _index in loads)


def affinity_schedule_projection(
    *,
    groups: int,
    attempts_per_group: int,
    verifier_slots: int,
    shared_prefix_cpu_fraction: float,
    replicas_per_group: int = 1,
    overhead_cpu_fraction_per_reuse: float = 0.0,
) -> dict[str, float | int | None]:
    """Project uniform-cost theorem-affinity execution in a saturated batch.

    Every independent attempt has normalized CPU cost one.  An affinity worker
    pays the exact shared prefix once, then every unchanged suffix assigned to
    that replica and the declared overhead for every reuse after its first
    attempt.  The batch latency model is deliberately discrete:
    independent attempts and affinity replicas each occupy one verifier slot
    and complete in whole waves.
    """
    for name, value in (
        ("groups", groups),
        ("attempts_per_group", attempts_per_group),
        ("verifier_slots", verifier_slots),
        ("replicas_per_group", replicas_per_group),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ProjectionError(f"{name} must be a positive integer")
    if attempts_per_group < 2:
        raise ProjectionError("attempts_per_group must be at least two")
    if replicas_per_group > attempts_per_group:
        raise ProjectionError("replicas_per_group cannot exceed attempts_per_group")
    if (
        isinstance(shared_prefix_cpu_fraction, bool)
        or not isinstance(shared_prefix_cpu_fraction, (int, float))
        or not math.isfinite(shared_prefix_cpu_fraction)
        or not 0.0 <= shared_prefix_cpu_fraction <= 1.0
    ):
        raise ProjectionError(
            "shared_prefix_cpu_fraction must be between zero and one"
        )
    if (
        isinstance(overhead_cpu_fraction_per_reuse, bool)
        or not isinstance(overhead_cpu_fraction_per_reuse, (int, float))
        or not math.isfinite(overhead_cpu_fraction_per_reuse)
        or overhead_cpu_fraction_per_reuse < 0.0
    ):
        raise ProjectionError(
            "overhead_cpu_fraction_per_reuse must be non-negative"
        )

    attempts = groups * attempts_per_group
    independent_waves = math.ceil(attempts / verifier_slots)
    affinity_waves = math.ceil(groups * replicas_per_group / verifier_slots)
    maximum_attempts_per_replica = math.ceil(
        attempts_per_group / replicas_per_group
    )
    affinity_replica_time = shared_prefix_cpu_fraction + (
        maximum_attempts_per_replica * (1.0 - shared_prefix_cpu_fraction)
    ) + (
        (maximum_attempts_per_replica - 1)
        * overhead_cpu_fraction_per_reuse
    )
    affinity_group_cpu = replicas_per_group * shared_prefix_cpu_fraction + (
        attempts_per_group * (1.0 - shared_prefix_cpu_fraction)
    ) + (
        (attempts_per_group - replicas_per_group)
        * overhead_cpu_fraction_per_reuse
    )
    affinity_cpu = groups * affinity_group_cpu
    affinity_batch_time = affinity_waves * affinity_replica_time
    if maximum_attempts_per_replica == 1:
        threshold = 0.0
    else:
        raw_threshold = (
            maximum_attempts_per_replica
            + (maximum_attempts_per_replica - 1)
            * overhead_cpu_fraction_per_reuse
            - independent_waves / affinity_waves
        ) / (maximum_attempts_per_replica - 1)
        threshold = None if raw_threshold > 1.0 else max(0.0, raw_threshold)

    reuses_per_group = attempts_per_group - replicas_per_group
    minimum_prefix_for_two_x_cpu = None
    if reuses_per_group:
        raw_minimum_prefix_for_two_x_cpu = (
            attempts_per_group / 2.0
            + reuses_per_group * overhead_cpu_fraction_per_reuse
        ) / reuses_per_group
        if raw_minimum_prefix_for_two_x_cpu <= 1.0:
            minimum_prefix_for_two_x_cpu = max(
                0.0, raw_minimum_prefix_for_two_x_cpu
            )
    cpu_headroom = None
    if reuses_per_group:
        zero_overhead_group_cpu = (
            replicas_per_group * shared_prefix_cpu_fraction
            + attempts_per_group * (1.0 - shared_prefix_cpu_fraction)
        )
        raw_cpu_headroom = (
            (attempts_per_group / 2.0 - zero_overhead_group_cpu)
            / reuses_per_group
        )
        cpu_headroom = (
            max(0.0, raw_cpu_headroom)
            if raw_cpu_headroom >= -1e-15
            else None
        )
    reuses_on_slowest_replica = maximum_attempts_per_replica - 1
    minimum_prefix_for_one_point_five_x_latency = None
    if reuses_on_slowest_replica:
        raw_minimum_prefix_for_one_point_five_x_latency = (
            maximum_attempts_per_replica
            + reuses_on_slowest_replica * overhead_cpu_fraction_per_reuse
            - independent_waves / (1.5 * affinity_waves)
        ) / reuses_on_slowest_replica
        if raw_minimum_prefix_for_one_point_five_x_latency <= 1.0:
            minimum_prefix_for_one_point_five_x_latency = max(
                0.0, raw_minimum_prefix_for_one_point_five_x_latency
            )
    latency_headroom = None
    if reuses_on_slowest_replica:
        zero_overhead_replica_time = shared_prefix_cpu_fraction + (
            maximum_attempts_per_replica
            * (1.0 - shared_prefix_cpu_fraction)
        )
        raw_latency_headroom = (
            (
                independent_waves / (1.5 * affinity_waves)
                - zero_overhead_replica_time
            )
            / reuses_on_slowest_replica
        )
        latency_headroom = (
            max(0.0, raw_latency_headroom)
            if raw_latency_headroom >= -1e-15
            else None
        )

    replica_sizes = [
        attempts_per_group // replicas_per_group
        + (1 if index < attempts_per_group % replicas_per_group else 0)
        for index in range(replicas_per_group)
    ]
    replica_job_costs = [
        shared_prefix_cpu_fraction
        + size * (1.0 - shared_prefix_cpu_fraction)
        + max(0, size - 1) * overhead_cpu_fraction_per_reuse
        for size in replica_sizes
    ]
    minimum_eligible_groups_for_joint_target = None
    joint_target_at_minimum_coverage_cpu_speedup = None
    joint_target_at_minimum_coverage_latency_speedup = None
    saving_per_eligible_group = attempts_per_group - affinity_group_cpu
    first_possible_cpu_group = groups + 1
    if saving_per_eligible_group > 0:
        first_possible_cpu_group = math.ceil(
            (attempts / 2.0) / saving_per_eligible_group
        )
    for eligible_groups in range(first_possible_cpu_group, groups + 1):
        mixed_cpu = (
            eligible_groups * affinity_group_cpu
            + (groups - eligible_groups) * attempts_per_group
        )
        mixed_jobs = replica_job_costs * eligible_groups + [1.0] * (
            (groups - eligible_groups) * attempts_per_group
        )
        mixed_makespan = _lpt_makespan(mixed_jobs, verifier_slots)
        mixed_cpu_speedup = attempts / mixed_cpu
        mixed_latency_speedup = independent_waves / mixed_makespan
        if mixed_cpu_speedup >= 2.0 and mixed_latency_speedup >= 1.5:
            minimum_eligible_groups_for_joint_target = eligible_groups
            joint_target_at_minimum_coverage_cpu_speedup = mixed_cpu_speedup
            joint_target_at_minimum_coverage_latency_speedup = (
                mixed_latency_speedup
            )
            break

    return {
        "groups": groups,
        "attempts_per_group": attempts_per_group,
        "replicas_per_group": replicas_per_group,
        "maximum_attempts_per_replica": maximum_attempts_per_replica,
        "attempts": attempts,
        "verifier_slots": verifier_slots,
        "shared_prefix_cpu_fraction": shared_prefix_cpu_fraction,
        "overhead_cpu_fraction_per_reuse": overhead_cpu_fraction_per_reuse,
        "independent_cpu": float(attempts),
        "affinity_cpu": affinity_cpu,
        "projected_cpu_throughput_multiplier": attempts / affinity_cpu,
        "independent_batch_waves": independent_waves,
        "affinity_replica_waves": affinity_waves,
        "affinity_group_waves": affinity_waves,
        "affinity_replica_normalized_time": affinity_replica_time,
        "affinity_group_normalized_cpu": affinity_group_cpu,
        "affinity_batch_normalized_time": affinity_batch_time,
        "projected_batch_latency_multiplier": (
            independent_waves / affinity_batch_time
        ),
        "minimum_shared_prefix_cpu_fraction_for_no_batch_latency_loss": threshold,
        "maximum_overhead_fraction_per_reuse_for_two_x_cpu": cpu_headroom,
        "maximum_overhead_fraction_per_reuse_for_one_point_five_x_batch_latency": (
            latency_headroom
        ),
        "minimum_shared_prefix_fraction_for_two_x_cpu": (
            minimum_prefix_for_two_x_cpu
        ),
        "minimum_shared_prefix_fraction_for_one_point_five_x_batch_latency": (
            minimum_prefix_for_one_point_five_x_latency
        ),
        "minimum_shared_prefix_fraction_for_joint_two_x_cpu_and_one_point_five_x_batch_latency": (
            max(
                minimum_prefix_for_two_x_cpu,
                minimum_prefix_for_one_point_five_x_latency,
            )
            if minimum_prefix_for_two_x_cpu is not None
            and minimum_prefix_for_one_point_five_x_latency is not None
            else None
        ),
        "minimum_eligible_groups_for_joint_two_x_cpu_and_one_point_five_x_batch_latency": (
            minimum_eligible_groups_for_joint_target
        ),
        "minimum_eligible_group_fraction_for_joint_two_x_cpu_and_one_point_five_x_batch_latency": (
            minimum_eligible_groups_for_joint_target / groups
            if minimum_eligible_groups_for_joint_target is not None
            else None
        ),
        "joint_target_at_minimum_coverage_cpu_speedup": (
            joint_target_at_minimum_coverage_cpu_speedup
        ),
        "joint_target_at_minimum_coverage_batch_latency_speedup": (
            joint_target_at_minimum_coverage_latency_speedup
        ),
    }


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
        raise ProjectionError(f"{path} must contain one JSON object")
    return value


def projected_speedup(
    reusable_cpu_fraction: float,
    application_acceleration: float,
    overhead_fraction: float,
) -> dict[str, float]:
    """Apply an Amdahl-style model to end-to-end independent CPU."""
    if not 0.0 <= reusable_cpu_fraction <= 1.0:
        raise ProjectionError("reusable CPU fraction must be between zero and one")
    if application_acceleration <= 1.0:
        raise ProjectionError("application acceleration must exceed one")
    if overhead_fraction < 0.0:
        raise ProjectionError("overhead fraction must be nonnegative")

    projected_cpu_fraction = (
        1.0
        - reusable_cpu_fraction
        + reusable_cpu_fraction / application_acceleration
        + overhead_fraction
    )
    return {
        "projected_cpu_fraction": projected_cpu_fraction,
        "projected_cpu_reduction_fraction": 1.0 - projected_cpu_fraction,
        "projected_throughput_multiplier": 1.0 / projected_cpu_fraction,
    }


def required_reusable_fraction(
    target_speedup: float,
    application_acceleration: float,
    overhead_fraction: float,
) -> float:
    """Solve the same model for the reusable CPU share needed by a target."""
    if target_speedup <= 1.0:
        raise ProjectionError("target speedup must exceed one")
    denominator = 1.0 - 1.0 / application_acceleration
    required = (1.0 + overhead_fraction - 1.0 / target_speedup) / denominator
    if required > 1.0:
        raise ProjectionError("target speedup is impossible under these assumptions")
    return required


def build_projection(
    prevalence_path: Path,
    probe_path: Path,
    *,
    shares: tuple[float, ...] = DEFAULT_SHARES,
    overhead_fraction: float = DEFAULT_OVERHEAD,
) -> dict[str, Any]:
    prevalence = _load(prevalence_path)
    probe = _load(probe_path)
    if prevalence.get("analysis") != "closing-certificate-prevalence-summary-v1":
        raise ProjectionError("unexpected prevalence report analysis identity")
    if probe.get("analysis") != "closing-certificate-feasibility-d024-v1":
        raise ProjectionError("unexpected probe report analysis identity")

    representative = prevalence["strata"]["representative"]
    enriched = prevalence["strata"]["enriched"]
    probe_pairs = probe["benchmarks"]
    accelerations = sorted(
        float(pair["generated_to_applied_plus_check_ratio"])
        for pair in probe_pairs
    )
    if not accelerations:
        raise ProjectionError("probe report contains no successful transfer pair")

    conservative_acceleration = accelerations[0]
    optimistic_acceleration = accelerations[-1]
    scenarios = []
    for share in shares:
        scenarios.append(
            {
                "reusable_expensive_closer_cpu_fraction": share,
                "conservative": projected_speedup(
                    share, conservative_acceleration, overhead_fraction
                ),
                "upper_sensitivity": projected_speedup(
                    share, optimistic_acceleration, overhead_fraction
                ),
            }
        )

    targets = {}
    for target in (1.5, 2.0, 3.0, 4.0):
        targets[str(target)] = required_reusable_fraction(
            target, conservative_acceleration, overhead_fraction
        )

    return {
        "analysis": "well-applicable-workload-projection-v1",
        "evidence_label": "Hypothesis",
        "claim_boundary": (
            "Sensitivity calculation, not a measured corpus result or deployment claim. "
            "It assumes the stated share of independent-verification CPU is spent in "
            "repeated, eligible expensive closing tactics."
        ),
        "inputs": {
            "prevalence": {
                "path": str(prevalence_path),
                "sha256": _sha256(prevalence_path),
            },
            "probe": {"path": str(probe_path), "sha256": _sha256(probe_path)},
        },
        "measured_anchors": {
            "representative": {
                "proposals": representative["proposals"],
                "verdict_agreements": representative["verdict_agreements"],
                "automatic_hits": representative["automatic_hits"],
                "cpu_reduction_fraction": representative["paired_cpu_saved_fraction"],
                "throughput_multiplier_from_cpu": (
                    representative["baseline_cpu_seconds"]
                    / representative["cached_cpu_seconds"]
                ),
            },
            "enriched_diagnostic": {
                "proposals": enriched["proposals"],
                "verdict_agreements": enriched["verdict_agreements"],
                "verdict_disagreement_count": len(enriched["verdict_disagreements"]),
                "cpu_reduction_fraction": enriched["paired_cpu_saved_fraction"],
                "throughput_multiplier_from_cpu": (
                    enriched["baseline_cpu_seconds"] / enriched["cached_cpu_seconds"]
                ),
            },
            "successful_transfer_acceleration_range": accelerations,
        },
        "model": {
            "formula": "cpu_fraction = 1 - f + f / A + o; speedup = 1 / cpu_fraction",
            "f": "share of end-to-end baseline CPU in reusable expensive closers",
            "A": "measured generation-plus-check/application-plus-check acceleration",
            "o": "assumed cache and orchestration overhead as share of baseline CPU",
            "overhead_fraction": overhead_fraction,
            "conservative_application_acceleration": conservative_acceleration,
            "upper_sensitivity_application_acceleration": optimistic_acceleration,
        },
        "scenarios": scenarios,
        "required_reusable_cpu_fraction_at_conservative_acceleration": targets,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prevalence",
        type=Path,
        default=Path("reports/c0_certificate_prevalence_d030.json"),
    )
    parser.add_argument(
        "--probe", type=Path, default=Path("reports/c0_certificate_probe.json")
    )
    parser.add_argument("--overhead-fraction", type=float, default=DEFAULT_OVERHEAD)
    args = parser.parse_args()
    report = build_projection(
        args.prevalence, args.probe, overhead_fraction=args.overhead_fraction
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
