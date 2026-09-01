"""Fail-closed opportunity screening for existing authentic checkpoint traces."""

from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable


TRACE_KIND = "shred-authentic-checkpoint-trace-v1"
VERDICTS = {"accepted", "rejected", "timed_out", "crashed"}
SHA256_LENGTH = 64
MINIMUM_QUALIFYING_GROUPS = 100
MINIMUM_QUALIFYING_THEOREMS = 10
MINIMUM_GROUP_ATTEMPTS = 8
MINIMUM_REUSABLE_PREFIX_CPU_FRACTION = 0.60
MAXIMUM_OVERHEAD_EQUIVALENT_PER_EIGHT_ATTEMPTS = 0.20
MINIMUM_PIPELINE_VERIFIER_CPU_FRACTION = 0.25
TARGET_VERIFIER_SPEEDUP = 2.0


class AuthenticTraceError(RuntimeError):
    """Raised when an existing-run trace cannot support an exact screen."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _records(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, mode="rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise AuthenticTraceError(
                    f"invalid JSON at {path}:{line_number}: {error}"
                ) from error
            if not isinstance(record, dict):
                raise AuthenticTraceError(
                    f"{path}:{line_number} must contain one JSON object"
                )
            yield line_number, record


def _string(record: dict[str, Any], field: str, location: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise AuthenticTraceError(f"missing non-empty {field} at {location}")
    return value


def _digest(record: dict[str, Any], field: str, location: str) -> str:
    value = _string(record, field, location)
    if len(value) != SHA256_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise AuthenticTraceError(f"invalid lowercase SHA-256 {field} at {location}")
    return value


def _seconds(record: dict[str, Any], field: str, location: str) -> float:
    value = record.get(field)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise AuthenticTraceError(f"invalid non-negative {field} at {location}")
    return float(value)


def _quantile(sorted_values: list[float], fraction: float) -> float | None:
    if not sorted_values:
        return None
    return sorted_values[int(fraction * (len(sorted_values) - 1))]


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise AuthenticTraceError(f"invalid manifest JSON: {error}") from error
    if not isinstance(value, dict):
        raise AuthenticTraceError("trace manifest must contain one JSON object")
    if value.get("schema_version") != 1 or value.get("trace_kind") != TRACE_KIND:
        raise AuthenticTraceError("unexpected authentic trace manifest identity")
    return value


def _validate_manifest(manifest: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    workload = manifest.get("workload")
    telemetry = manifest.get("telemetry")
    partitions = manifest.get("partitions")
    if not isinstance(workload, dict) or not isinstance(telemetry, dict):
        raise AuthenticTraceError("manifest requires workload and telemetry objects")
    for field in (
        "name",
        "dataset_revision",
        "producer_git_commit",
        "producer_command",
        "lean_revision",
        "mathlib_revision",
        "hardware",
    ):
        _string(workload, field, "manifest workload")
    _digest(workload, "resolved_configuration_sha256", "manifest workload")
    if not isinstance(workload.get("producer_git_dirty"), bool):
        raise AuthenticTraceError("workload producer_git_dirty must be boolean")
    expected = workload.get("expected_attempts")
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 1:
        raise AuthenticTraceError("workload expected_attempts must be positive")
    concurrency = workload.get("concurrency")
    if (
        isinstance(concurrency, bool)
        or not isinstance(concurrency, int)
        or concurrency < 1
    ):
        raise AuthenticTraceError("workload concurrency must be positive")
    _seconds(workload, "timeout_seconds", "manifest workload")
    memory = workload.get("memory_limit_bytes")
    if isinstance(memory, bool) or not isinstance(memory, int) or memory < 1:
        raise AuthenticTraceError("workload memory_limit_bytes must be positive")
    required_telemetry = {
        "lineage_kind": "lean_native_exact_prefix",
        "cpu_clock": "process_cpu",
        "full_cpu_semantics": "warm_independent_complete_attempt",
        "prefix_cpu_semantics": "same_attempt_through_exact_checkpoint",
        "verdict_authority": "ordinary_lean",
    }
    for field, expected_value in required_telemetry.items():
        if telemetry.get(field) != expected_value:
            raise AuthenticTraceError(
                f"telemetry {field} must equal {expected_value!r}"
            )
    if not isinstance(partitions, list) or not partitions:
        raise AuthenticTraceError("manifest requires at least one partition")
    return expected, partitions


def screen_authentic_trace(
    manifest_path: Path,
    *,
    source_root: Path | None = None,
    overhead_budget_cpu_seconds_per_hit: float | None = None,
    overhead_budget_source: str | None = None,
) -> dict[str, Any]:
    """Validate an immutable existing-run trace and project exact checkpoint reuse.

    The projection executes each qualifying prefix once at the maximum observed
    prefix CPU in its group, preserves every suffix cost, and adds the registered
    per-hit overhead budget. It never executes Lean or changes a verdict.
    """
    if (overhead_budget_cpu_seconds_per_hit is None) != (
        overhead_budget_source is None
    ):
        raise AuthenticTraceError(
            "overhead budget and its source must be supplied together"
        )
    if (
        overhead_budget_cpu_seconds_per_hit is not None
        and (
            not math.isfinite(overhead_budget_cpu_seconds_per_hit)
            or overhead_budget_cpu_seconds_per_hit < 0
        )
    ):
        raise AuthenticTraceError("overhead budget must be non-negative")
    if overhead_budget_source is not None and not overhead_budget_source.strip():
        raise AuthenticTraceError("overhead budget source must be non-empty")

    manifest_path = manifest_path.resolve()
    manifest = _load_manifest(manifest_path)
    expected_attempts, partitions = _validate_manifest(manifest)
    source_root_default = manifest.get("source_root_default", ".")
    if not isinstance(source_root_default, str) or not source_root_default:
        raise AuthenticTraceError("source_root_default must be a non-empty string")
    root = source_root.resolve() if source_root is not None else (
        manifest_path.parent / source_root_default
    ).resolve()

    attempts: list[dict[str, Any]] = []
    proposal_ids: set[str] = set()
    partition_receipts = []
    checkpoint_identities: dict[str, tuple[str, ...]] = {}
    physical_records = 0
    for partition in partitions:
        if not isinstance(partition, dict):
            raise AuthenticTraceError("partition entries must be objects")
        path = (root / _string(partition, "path", "manifest partition")).resolve()
        if not path.is_relative_to(root):
            raise AuthenticTraceError(f"trace partition escapes source root: {path}")
        if not path.is_file():
            raise AuthenticTraceError(f"missing trace partition: {path}")
        expected_sha256 = _digest(partition, "sha256", "manifest partition")
        observed_sha256 = _sha256(path)
        if observed_sha256 != expected_sha256:
            raise AuthenticTraceError(f"trace partition checksum mismatch: {path}")
        declared_records = partition.get("records")
        if (
            isinstance(declared_records, bool)
            or not isinstance(declared_records, int)
            or declared_records < 0
        ):
            raise AuthenticTraceError(f"invalid partition record count: {path}")
        rows = 0
        for line_number, record in _records(path):
            rows += 1
            physical_records += 1
            location = f"{path}:{line_number}"
            proposal_id = _string(record, "proposal_id", location)
            if proposal_id in proposal_ids:
                raise AuthenticTraceError(f"duplicate proposal_id {proposal_id!r}")
            proposal_ids.add(proposal_id)
            theorem_name = _string(record, "theorem_name", location)
            proposal_sha256 = _digest(record, "proposal_sha256", location)
            theorem_sha256 = _digest(record, "theorem_statement_sha256", location)
            verdict = _string(record, "verdict", location)
            if verdict not in VERDICTS:
                raise AuthenticTraceError(f"invalid verdict at {location}: {verdict}")
            full_cpu = _seconds(record, "full_verifier_cpu_seconds", location)
            eligibility = _string(record, "eligibility", location)
            normalized = {
                "proposal_id": proposal_id,
                "proposal_sha256": proposal_sha256,
                "theorem_name": theorem_name,
                "theorem_statement_sha256": theorem_sha256,
                "verdict": verdict,
                "full_cpu": full_cpu,
                "eligibility": eligibility,
            }
            if eligibility == "fallback":
                normalized["fallback_reason"] = _string(
                    record, "fallback_reason", location
                )
                forbidden = {
                    "prefix_verifier_cpu_seconds",
                    "parent_environment_sha256",
                    "root_context_sha256",
                    "prefix_edges_sha256",
                    "checkpoint_artifact_sha256",
                }.intersection(record)
                if forbidden:
                    raise AuthenticTraceError(
                        f"fallback record carries exact-checkpoint fields at {location}"
                    )
            elif eligibility == "exact_checkpoint":
                if "fallback_reason" in record:
                    raise AuthenticTraceError(
                        f"exact-checkpoint record carries fallback_reason at {location}"
                    )
                prefix_cpu = _seconds(
                    record, "prefix_verifier_cpu_seconds", location
                )
                if prefix_cpu > full_cpu:
                    raise AuthenticTraceError(
                        f"prefix CPU exceeds full CPU at {location}"
                    )
                identity = (
                    theorem_name,
                    theorem_sha256,
                    _digest(record, "parent_environment_sha256", location),
                    _digest(record, "root_context_sha256", location),
                    _digest(record, "prefix_edges_sha256", location),
                )
                checkpoint_sha256 = _digest(
                    record, "checkpoint_artifact_sha256", location
                )
                prior_identity = checkpoint_identities.setdefault(
                    checkpoint_sha256, identity
                )
                if prior_identity != identity:
                    raise AuthenticTraceError(
                        "one checkpoint artifact digest has conflicting exact identity"
                    )
                normalized.update(
                    {
                        "prefix_cpu": prefix_cpu,
                        "checkpoint_sha256": checkpoint_sha256,
                        "group_key": (*identity, checkpoint_sha256),
                    }
                )
            else:
                raise AuthenticTraceError(
                    f"eligibility must be exact_checkpoint or fallback at {location}"
                )
            attempts.append(normalized)
        if rows != declared_records:
            raise AuthenticTraceError(
                f"partition count mismatch for {path}: {rows} != {declared_records}"
            )
        partition_receipts.append(
            {"path": str(path), "sha256": observed_sha256, "records": rows}
        )

    if physical_records != expected_attempts:
        raise AuthenticTraceError(
            f"attempt accounting mismatch: {physical_records} != {expected_attempts}"
        )

    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    verdicts: Counter[str] = Counter()
    fallback_reasons: Counter[str] = Counter()
    theorem_costs: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {
            "attempts": 0,
            "baseline_cpu_seconds": 0.0,
            "ideal_projected_cpu_seconds": 0.0,
            "projected_cpu_seconds": 0.0,
            "qualifying_groups": 0,
            "cache_hits": 0,
        }
    )
    baseline_cpu = 0.0
    for attempt in attempts:
        verdicts[attempt["verdict"]] += 1
        baseline_cpu += attempt["full_cpu"]
        theorem = theorem_costs[attempt["theorem_name"]]
        theorem["attempts"] += 1
        theorem["baseline_cpu_seconds"] += attempt["full_cpu"]
        theorem["ideal_projected_cpu_seconds"] += attempt["full_cpu"]
        theorem["projected_cpu_seconds"] += attempt["full_cpu"]
        if attempt["eligibility"] == "fallback":
            fallback_reasons[attempt["fallback_reason"]] += 1
        else:
            groups[attempt["group_key"]].append(attempt)
    if baseline_cpu <= 0:
        raise AuthenticTraceError("trace has no positive verifier CPU")

    qualifying_groups = []
    insufficient_attempts = 0
    ideal_saved_cpu = 0.0
    cache_hits = 0
    qualifying_baseline_cpu = 0.0
    for key in sorted(groups):
        group = groups[key]
        if len(group) < MINIMUM_GROUP_ATTEMPTS:
            insufficient_attempts += len(group)
            continue
        prefix_sum = sum(item["prefix_cpu"] for item in group)
        shared_prefix_cpu = max(item["prefix_cpu"] for item in group)
        saved = prefix_sum - shared_prefix_cpu
        hits = len(group) - 1
        ideal_saved_cpu += saved
        cache_hits += hits
        group_baseline_cpu = sum(item["full_cpu"] for item in group)
        qualifying_baseline_cpu += group_baseline_cpu
        theorem = theorem_costs[group[0]["theorem_name"]]
        theorem["ideal_projected_cpu_seconds"] -= saved
        theorem["projected_cpu_seconds"] -= saved
        theorem["qualifying_groups"] += 1
        theorem["cache_hits"] += hits
        qualifying_groups.append(
            {
                "theorem_name": group[0]["theorem_name"],
                "checkpoint_artifact_sha256": group[0]["checkpoint_sha256"],
                "attempts": len(group),
                "cache_hits": hits,
                "baseline_cpu_seconds": group_baseline_cpu,
                "repeated_prefix_cpu_seconds": prefix_sum,
                "shared_prefix_cpu_seconds": shared_prefix_cpu,
                "ideal_saved_cpu_seconds": saved,
            }
        )

    ideal_projected_cpu = baseline_cpu - ideal_saved_cpu
    ideal_speedup = baseline_cpu / ideal_projected_cpu
    overhead_total = None
    projected_cpu = None
    projected_speedup = None
    if overhead_budget_cpu_seconds_per_hit is not None:
        overhead_total = overhead_budget_cpu_seconds_per_hit * cache_hits
        projected_cpu = ideal_projected_cpu + overhead_total
        projected_speedup = baseline_cpu / projected_cpu
        for theorem in theorem_costs.values():
            theorem["projected_cpu_seconds"] += (
                overhead_budget_cpu_seconds_per_hit * theorem["cache_hits"]
            )

    theorem_rows = []
    for theorem_name in sorted(theorem_costs):
        values = theorem_costs[theorem_name]
        theorem_baseline = float(values["baseline_cpu_seconds"])
        ideal_cost = float(values["ideal_projected_cpu_seconds"])
        projected_cost = (
            float(values["projected_cpu_seconds"])
            if overhead_budget_cpu_seconds_per_hit is not None
            else None
        )
        theorem_rows.append(
            {
                "theorem_name": theorem_name,
                **values,
                "ideal_verifier_speedup": (
                    theorem_baseline / ideal_cost
                    if theorem_baseline > 0 and ideal_cost > 0
                    else None
                ),
                "projected_verifier_speedup": (
                    theorem_baseline / projected_cost
                    if theorem_baseline > 0
                    and projected_cost is not None
                    and projected_cost > 0
                    else None
                ),
            }
        )
    speedups = sorted(
        float(row["projected_verifier_speedup"])
        for row in theorem_rows
        if row["projected_verifier_speedup"] is not None
    )
    tails = {
        name: _quantile(speedups, fraction)
        for name, fraction in (
            ("p10", 0.10),
            ("median", 0.50),
            ("p90", 0.90),
            ("p95", 0.95),
            ("p99", 0.99),
        )
    }

    maximum_total_overhead_for_target = max(
        0.0, baseline_cpu / TARGET_VERIFIER_SPEEDUP - ideal_projected_cpu
    )
    maximum_overhead_per_hit = (
        maximum_total_overhead_for_target / cache_hits if cache_hits else 0.0
    )
    workload = manifest["workload"]
    pipeline_projection = None
    pipeline_verifier_fraction = None
    if "pipeline_total_cpu_seconds" in workload:
        pipeline_cpu = _seconds(
            workload, "pipeline_total_cpu_seconds", "manifest workload"
        )
        if pipeline_cpu < baseline_cpu:
            raise AuthenticTraceError(
                "pipeline total CPU cannot be below traced verifier CPU"
            )
        pipeline_projection = {
            "baseline_cpu_seconds": pipeline_cpu,
            "verifier_cpu_fraction": baseline_cpu / pipeline_cpu,
            "ideal_speedup": pipeline_cpu
            / (pipeline_cpu - baseline_cpu + ideal_projected_cpu),
            "projected_speedup": (
                pipeline_cpu / (pipeline_cpu - baseline_cpu + projected_cpu)
                if projected_cpu is not None
                else None
            ),
        }
        pipeline_verifier_fraction = baseline_cpu / pipeline_cpu

    qualifying_theorems = {group["theorem_name"] for group in qualifying_groups}
    reusable_prefix_cpu_fraction = ideal_saved_cpu / baseline_cpu
    maximum_registered_overhead = (
        MAXIMUM_OVERHEAD_EQUIVALENT_PER_EIGHT_ATTEMPTS
        * qualifying_baseline_cpu
        / 8.0
    )
    criteria = {
        "has_qualifying_groups": bool(qualifying_groups),
        "group_coverage": len(qualifying_groups) >= MINIMUM_QUALIFYING_GROUPS,
        "theorem_coverage": len(qualifying_theorems) >= MINIMUM_QUALIFYING_THEOREMS,
        "reusable_prefix_cpu_fraction": reusable_prefix_cpu_fraction
        >= MINIMUM_REUSABLE_PREFIX_CPU_FRACTION,
        "registered_overhead_present": overhead_total is not None,
        "registered_overhead_within_limit": (
            overhead_total is not None and overhead_total <= maximum_registered_overhead
        ),
        "pipeline_cpu_present": pipeline_projection is not None,
        "pipeline_verifier_cpu_material": (
            pipeline_verifier_fraction is not None
            and pipeline_verifier_fraction >= MINIMUM_PIPELINE_VERIFIER_CPU_FRACTION
        ),
        "target_verifier_speedup": (
            projected_speedup is not None
            and projected_speedup >= TARGET_VERIFIER_SPEEDUP
        ),
    }
    if not criteria["has_qualifying_groups"]:
        decision = "stop_no_qualifying_exact_checkpoint_groups"
    elif not criteria["group_coverage"] or not criteria["theorem_coverage"]:
        decision = "stop_insufficient_authentic_coverage"
    elif not criteria["reusable_prefix_cpu_fraction"]:
        decision = "stop_below_reusable_prefix_cpu_gate"
    elif not criteria["registered_overhead_present"]:
        decision = "inconclusive_missing_registered_overhead_budget"
    elif not criteria["registered_overhead_within_limit"]:
        decision = "stop_overhead_budget_exceeds_gate"
    elif not criteria["pipeline_cpu_present"]:
        decision = "inconclusive_missing_pipeline_cpu"
    elif not criteria["pipeline_verifier_cpu_material"]:
        decision = "stop_verifier_cpu_not_material_to_pipeline"
    elif not criteria["target_verifier_speedup"]:
        decision = "stop_below_target_verifier_speedup"
    else:
        decision = "read_only_value_gate_passed"

    return {
        "analysis": "authentic-checkpoint-trace-screen-v1",
        "evidence_label": "Observed trace accounting; Hypothesis projection",
        "claim_boundary": (
            "Read-only opportunity screen, not a measured SHRED speedup or verdict-equivalence result"
        ),
        "inputs": {
            "manifest": str(manifest_path),
            "manifest_sha256": _sha256(manifest_path),
            "partitions": partition_receipts,
        },
        "configuration": {
            "minimum_group_attempts": MINIMUM_GROUP_ATTEMPTS,
            "target_verifier_speedup": TARGET_VERIFIER_SPEEDUP,
            "minimum_qualifying_groups": MINIMUM_QUALIFYING_GROUPS,
            "minimum_qualifying_theorems": MINIMUM_QUALIFYING_THEOREMS,
            "minimum_reusable_prefix_cpu_fraction": (
                MINIMUM_REUSABLE_PREFIX_CPU_FRACTION
            ),
            "maximum_overhead_equivalent_per_eight_attempts": (
                MAXIMUM_OVERHEAD_EQUIVALENT_PER_EIGHT_ATTEMPTS
            ),
            "minimum_pipeline_verifier_cpu_fraction": (
                MINIMUM_PIPELINE_VERIFIER_CPU_FRACTION
            ),
            "overhead_budget_cpu_seconds_per_hit": overhead_budget_cpu_seconds_per_hit,
            "overhead_budget_source": overhead_budget_source,
        },
        "accounting": {
            "expected_attempts": expected_attempts,
            "physical_attempts": physical_records,
            "exact_checkpoint_attempts": sum(len(group) for group in groups.values()),
            "qualifying_exact_checkpoint_attempts": sum(
                group["attempts"] for group in qualifying_groups
            ),
            "insufficient_group_attempts": insufficient_attempts,
            "fallback_attempts": sum(fallback_reasons.values()),
            "fallback_reasons": dict(sorted(fallback_reasons.items())),
            "verdicts": dict(sorted(verdicts.items())),
            "qualifying_groups": len(qualifying_groups),
            "qualifying_theorems": len(qualifying_theorems),
            "cache_hits": cache_hits,
        },
        "verifier_cpu": {
            "baseline_seconds": baseline_cpu,
            "ideal_projected_seconds": ideal_projected_cpu,
            "ideal_saved_seconds": ideal_saved_cpu,
            "reusable_prefix_cpu_fraction": reusable_prefix_cpu_fraction,
            "ideal_speedup": ideal_speedup,
            "registered_overhead_seconds": overhead_total,
            "projected_seconds": projected_cpu,
            "projected_speedup": projected_speedup,
            "maximum_total_overhead_seconds_for_target": maximum_total_overhead_for_target,
            "maximum_overhead_seconds_per_hit_for_target": maximum_overhead_per_hit,
            "maximum_registered_overhead_seconds": maximum_registered_overhead,
        },
        "pipeline_cpu": pipeline_projection,
        "per_theorem_speedup_quantiles": tails,
        "per_theorem": theorem_rows,
        "qualifying_group_details": qualifying_groups,
        "gate": {
            "passes": decision == "read_only_value_gate_passed",
            "decision": decision,
            "criteria": criteria,
            "next_step": (
                "propose one bounded paired implementation experiment under D-036"
                if decision == "read_only_value_gate_passed"
                else "do not run a SHRED implementation benchmark"
            ),
        },
    }
