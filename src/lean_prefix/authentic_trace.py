"""Fail-closed opportunity screening for existing authentic checkpoint traces."""

from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable


TRACE_SCHEMA_VERSION = 2
TRACE_KIND = "shred-authentic-checkpoint-trace-v2"
VERDICTS = {"accepted", "rejected", "timed_out", "crashed"}
SHA256_LENGTH = 64
MINIMUM_QUALIFYING_GROUPS = 100
MINIMUM_QUALIFYING_THEOREMS = 10
MINIMUM_GROUP_ATTEMPTS = 8
MINIMUM_EXECUTION_SCOPES = 2
MINIMUM_PROCESS_LOCAL_REUSABLE_CPU_FRACTION = 0.60
MINIMUM_PORTABLE_INCREMENTAL_CPU_FRACTION = 0.60
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
    if (
        value.get("schema_version") != TRACE_SCHEMA_VERSION
        or value.get("trace_kind") != TRACE_KIND
    ):
        raise AuthenticTraceError("unexpected authentic trace manifest identity")
    allowed_fields = {
        "schema_version",
        "trace_kind",
        "source_root_default",
        "workload",
        "telemetry",
        "partitions",
    }
    unexpected = set(value).difference(allowed_fields)
    if unexpected:
        raise AuthenticTraceError(
            f"unexpected authentic trace manifest fields: {sorted(unexpected)}"
        )
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
    unexpected_telemetry = set(telemetry).difference(required_telemetry)
    if unexpected_telemetry:
        raise AuthenticTraceError(
            f"unexpected telemetry fields: {sorted(unexpected_telemetry)}"
        )
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
    portable_overhead_budget_cpu_seconds_per_hit: float | None = None,
    portable_overhead_budget_source: str | None = None,
    process_local_overhead_budget_cpu_seconds_per_hit: float | None = None,
    process_local_overhead_budget_source: str | None = None,
) -> dict[str, Any]:
    """Validate an immutable existing-run trace and project exact checkpoint reuse.

    The projection executes each qualifying prefix once at the maximum observed
    prefix CPU in its group, preserves every suffix cost, and adds independent
    registered budgets for process-local branching and portable loading. The
    historical ``overhead_budget_*`` keywords alias only the portable budget.
    It never executes Lean or changes a verdict.
    """
    if (
        overhead_budget_cpu_seconds_per_hit is not None
        or overhead_budget_source is not None
    ) and (
        portable_overhead_budget_cpu_seconds_per_hit is not None
        or portable_overhead_budget_source is not None
    ):
        raise AuthenticTraceError(
            "use either portable overhead arguments or their historical aliases"
        )
    if portable_overhead_budget_cpu_seconds_per_hit is not None:
        overhead_budget_cpu_seconds_per_hit = (
            portable_overhead_budget_cpu_seconds_per_hit
        )
    if portable_overhead_budget_source is not None:
        overhead_budget_source = portable_overhead_budget_source
    if (overhead_budget_cpu_seconds_per_hit is None) != (
        overhead_budget_source is None
    ):
        raise AuthenticTraceError(
            "overhead budget and its source must be supplied together"
        )
    if (
        overhead_budget_cpu_seconds_per_hit is not None
        and (
            isinstance(overhead_budget_cpu_seconds_per_hit, bool)
            or not isinstance(overhead_budget_cpu_seconds_per_hit, (int, float))
            or not math.isfinite(overhead_budget_cpu_seconds_per_hit)
            or overhead_budget_cpu_seconds_per_hit < 0
        )
    ):
        raise AuthenticTraceError("overhead budget must be non-negative")
    if overhead_budget_source is not None and not overhead_budget_source.strip():
        raise AuthenticTraceError("overhead budget source must be non-empty")
    if (process_local_overhead_budget_cpu_seconds_per_hit is None) != (
        process_local_overhead_budget_source is None
    ):
        raise AuthenticTraceError(
            "process-local overhead budget and its source must be supplied together"
        )
    if (
        process_local_overhead_budget_cpu_seconds_per_hit is not None
        and (
            isinstance(process_local_overhead_budget_cpu_seconds_per_hit, bool)
            or not isinstance(
                process_local_overhead_budget_cpu_seconds_per_hit, (int, float)
            )
            or not math.isfinite(
                process_local_overhead_budget_cpu_seconds_per_hit
            )
            or process_local_overhead_budget_cpu_seconds_per_hit < 0
        )
    ):
        raise AuthenticTraceError("process-local overhead budget must be non-negative")
    if (
        process_local_overhead_budget_source is not None
        and not process_local_overhead_budget_source.strip()
    ):
        raise AuthenticTraceError(
            "process-local overhead budget source must be non-empty"
        )

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
        unexpected_partition_fields = set(partition).difference(
            {"path", "sha256", "records"}
        )
        if unexpected_partition_fields:
            raise AuthenticTraceError(
                "unexpected partition fields: "
                f"{sorted(unexpected_partition_fields)}"
            )
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
                    "execution_scope_sha256",
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
                execution_scope_sha256 = _digest(
                    record, "execution_scope_sha256", location
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
                        "execution_scope_sha256": execution_scope_sha256,
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
            "process_local_counterfactual_cpu_seconds": 0.0,
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
        theorem["process_local_counterfactual_cpu_seconds"] += attempt["full_cpu"]
        theorem["ideal_projected_cpu_seconds"] += attempt["full_cpu"]
        theorem["projected_cpu_seconds"] += attempt["full_cpu"]
        if attempt["eligibility"] == "fallback":
            fallback_reasons[attempt["fallback_reason"]] += 1
        else:
            groups[attempt["group_key"]].append(attempt)
    if baseline_cpu <= 0:
        raise AuthenticTraceError("trace has no positive verifier CPU")

    local_scope_groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(
        list
    )
    for group_key, group in groups.items():
        for attempt in group:
            local_scope_groups[
                (*group_key, attempt["execution_scope_sha256"])
            ].append(attempt)

    local_qualifying_groups = []
    local_insufficient_attempts = 0
    local_saved_cpu = 0.0
    local_cache_hits = 0
    local_qualifying_baseline_cpu = 0.0
    local_theorem_costs: dict[str, dict[str, float | int]] = {
        theorem_name: {
            "attempts": int(values["attempts"]),
            "baseline_cpu_seconds": float(values["baseline_cpu_seconds"]),
            "ideal_projected_cpu_seconds": float(values["baseline_cpu_seconds"]),
            "projected_cpu_seconds": float(values["baseline_cpu_seconds"]),
            "qualifying_groups": 0,
            "cache_hits": 0,
        }
        for theorem_name, values in theorem_costs.items()
    }
    for key in sorted(local_scope_groups):
        group = local_scope_groups[key]
        if len(group) < MINIMUM_GROUP_ATTEMPTS:
            local_insufficient_attempts += len(group)
            continue
        prefix_sum = sum(item["prefix_cpu"] for item in group)
        shared_prefix_cpu = max(item["prefix_cpu"] for item in group)
        saved = prefix_sum - shared_prefix_cpu
        hits = len(group) - 1
        group_baseline_cpu = sum(item["full_cpu"] for item in group)
        local_saved_cpu += saved
        local_cache_hits += hits
        local_qualifying_baseline_cpu += group_baseline_cpu
        theorem = local_theorem_costs[group[0]["theorem_name"]]
        theorem["ideal_projected_cpu_seconds"] -= saved
        theorem["projected_cpu_seconds"] -= saved
        theorem["qualifying_groups"] += 1
        theorem["cache_hits"] += hits
        local_qualifying_groups.append(
            {
                "theorem_name": group[0]["theorem_name"],
                "checkpoint_artifact_sha256": group[0]["checkpoint_sha256"],
                "execution_scope_sha256": group[0]["execution_scope_sha256"],
                "attempts": len(group),
                "cache_hits": hits,
                "baseline_cpu_seconds": group_baseline_cpu,
                "repeated_prefix_cpu_seconds": prefix_sum,
                "shared_prefix_cpu_seconds": shared_prefix_cpu,
                "ideal_saved_cpu_seconds": saved,
            }
        )

    local_ideal_projected_cpu = baseline_cpu - local_saved_cpu
    local_ideal_speedup = baseline_cpu / local_ideal_projected_cpu
    local_overhead_total = None
    local_projected_cpu = None
    local_projected_speedup = None
    if process_local_overhead_budget_cpu_seconds_per_hit is not None:
        local_overhead_total = (
            process_local_overhead_budget_cpu_seconds_per_hit * local_cache_hits
        )
        local_projected_cpu = local_ideal_projected_cpu + local_overhead_total
        local_projected_speedup = baseline_cpu / local_projected_cpu
        for theorem in local_theorem_costs.values():
            theorem["projected_cpu_seconds"] += (
                process_local_overhead_budget_cpu_seconds_per_hit
                * theorem["cache_hits"]
            )

    local_replication_frontier = []
    if local_qualifying_groups:
        maximum_replicas = max(
            int(group["attempts"]) for group in local_qualifying_groups
        )
        for replicas in range(1, maximum_replicas + 1):
            reused_attempts = sum(
                max(0, int(group["attempts"]) - replicas)
                for group in local_qualifying_groups
            )
            # Without retaining proposal-level scheduling choices, the sum of
            # per-replica prefix maxima is bounded above by k times the global
            # maximum (and by executing every prefix independently). Charging
            # that upper bound makes this frontier conservative under observed
            # prefix-cost variation while remaining exact at k=1 and k=n.
            replicated_prefix_cpu = sum(
                min(
                    float(group["repeated_prefix_cpu_seconds"]),
                    replicas * float(group["shared_prefix_cpu_seconds"]),
                )
                for group in local_qualifying_groups
            )
            repeated_prefix_cpu = sum(
                float(group["repeated_prefix_cpu_seconds"])
                for group in local_qualifying_groups
            )
            saved_cpu = repeated_prefix_cpu - replicated_prefix_cpu
            ideal_cpu = baseline_cpu - saved_cpu
            registered_overhead = None
            projected_cpu_for_replicas = None
            projected_speedup_for_replicas = None
            if process_local_overhead_budget_cpu_seconds_per_hit is not None:
                registered_overhead = (
                    process_local_overhead_budget_cpu_seconds_per_hit
                    * reused_attempts
                )
                projected_cpu_for_replicas = ideal_cpu + registered_overhead
                projected_speedup_for_replicas = (
                    baseline_cpu / projected_cpu_for_replicas
                )
            local_replication_frontier.append(
                {
                    "replicas_per_group": replicas,
                    "independently_executed_prefixes": (
                        sum(
                            min(replicas, int(group["attempts"]))
                            for group in local_qualifying_groups
                        )
                    ),
                    "reused_attempts": reused_attempts,
                    "conservative_replicated_prefix_cpu_seconds": (
                        replicated_prefix_cpu
                    ),
                    "conservative_saved_cpu_seconds": saved_cpu,
                    "conservative_saved_fraction_of_baseline": (
                        saved_cpu / baseline_cpu
                    ),
                    "ideal_projected_cpu_seconds": ideal_cpu,
                    "ideal_cpu_speedup": baseline_cpu / ideal_cpu,
                    "registered_overhead_seconds": registered_overhead,
                    "projected_cpu_seconds": projected_cpu_for_replicas,
                    "projected_cpu_speedup": projected_speedup_for_replicas,
                }
            )

    local_theorem_rows = []
    for theorem_name in sorted(local_theorem_costs):
        values = local_theorem_costs[theorem_name]
        theorem_baseline = float(values["baseline_cpu_seconds"])
        ideal_cost = float(values["ideal_projected_cpu_seconds"])
        projected_cost = (
            float(values["projected_cpu_seconds"])
            if process_local_overhead_budget_cpu_seconds_per_hit is not None
            else None
        )
        local_theorem_rows.append(
            {
                "theorem_name": theorem_name,
                **values,
                "ideal_speedup": (
                    theorem_baseline / ideal_cost
                    if theorem_baseline > 0 and ideal_cost > 0
                    else None
                ),
                "projected_speedup": (
                    theorem_baseline / projected_cost
                    if theorem_baseline > 0
                    and projected_cost is not None
                    and projected_cost > 0
                    else None
                ),
            }
        )
    local_speedups = sorted(
        float(row["projected_speedup"])
        for row in local_theorem_rows
        if row["projected_speedup"] is not None
    )
    local_tails = {
        name: _quantile(local_speedups, fraction)
        for name, fraction in (
            ("p10", 0.10),
            ("median", 0.50),
            ("p90", 0.90),
            ("p95", 0.95),
            ("p99", 0.99),
        )
    }

    qualifying_groups = []
    insufficient_attempts = 0
    single_scope_attempts = 0
    single_scope_groups = 0
    single_scope_baseline_cpu = 0.0
    single_scope_ideal_saved_cpu = 0.0
    qualifying_process_local_saved_cpu = 0.0
    portable_incremental_saved_cpu = 0.0
    ideal_saved_cpu = 0.0
    cache_hits = 0
    qualifying_baseline_cpu = 0.0
    for key in sorted(groups):
        group = groups[key]
        if len(group) < MINIMUM_GROUP_ATTEMPTS:
            insufficient_attempts += len(group)
            continue
        execution_scopes = {item["execution_scope_sha256"] for item in group}
        prefix_sum = sum(item["prefix_cpu"] for item in group)
        shared_prefix_cpu = max(item["prefix_cpu"] for item in group)
        scope_prefix_cpu = sum(
            max(
                item["prefix_cpu"]
                for item in group
                if item["execution_scope_sha256"] == scope
            )
            for scope in execution_scopes
        )
        if len(execution_scopes) < MINIMUM_EXECUTION_SCOPES:
            single_scope_attempts += len(group)
            single_scope_groups += 1
            single_scope_baseline_cpu += sum(item["full_cpu"] for item in group)
            single_scope_ideal_saved_cpu += prefix_sum - shared_prefix_cpu
            continue
        process_local_saved = prefix_sum - scope_prefix_cpu
        portable_incremental_saved = scope_prefix_cpu - shared_prefix_cpu
        qualifying_process_local_saved_cpu += process_local_saved
        portable_incremental_saved_cpu += portable_incremental_saved
        saved = prefix_sum - shared_prefix_cpu
        hits = len(group) - 1
        ideal_saved_cpu += saved
        cache_hits += hits
        group_baseline_cpu = sum(item["full_cpu"] for item in group)
        qualifying_baseline_cpu += group_baseline_cpu
        theorem = theorem_costs[group[0]["theorem_name"]]
        theorem["process_local_counterfactual_cpu_seconds"] -= process_local_saved
        theorem["ideal_projected_cpu_seconds"] -= saved
        theorem["projected_cpu_seconds"] -= saved
        theorem["qualifying_groups"] += 1
        theorem["cache_hits"] += hits
        qualifying_groups.append(
            {
                "theorem_name": group[0]["theorem_name"],
                "checkpoint_artifact_sha256": group[0]["checkpoint_sha256"],
                "attempts": len(group),
                "execution_scopes": len(execution_scopes),
                "cache_hits": hits,
                "baseline_cpu_seconds": group_baseline_cpu,
                "repeated_prefix_cpu_seconds": prefix_sum,
                "shared_prefix_cpu_seconds": shared_prefix_cpu,
                "process_local_saved_cpu_seconds": process_local_saved,
                "portable_incremental_saved_cpu_seconds": portable_incremental_saved,
                "ideal_saved_cpu_seconds": saved,
            }
        )

    ideal_projected_cpu = baseline_cpu - ideal_saved_cpu
    ideal_speedup = baseline_cpu / ideal_projected_cpu
    process_local_projected_cpu = baseline_cpu - qualifying_process_local_saved_cpu
    portable_incremental_cpu_fraction = portable_incremental_saved_cpu / baseline_cpu
    portable_incremental_ideal_speedup = (
        process_local_projected_cpu / ideal_projected_cpu
    )
    overhead_total = None
    projected_cpu = None
    projected_speedup = None
    portable_incremental_projected_speedup = None
    if overhead_budget_cpu_seconds_per_hit is not None:
        overhead_total = overhead_budget_cpu_seconds_per_hit * cache_hits
        projected_cpu = ideal_projected_cpu + overhead_total
        projected_speedup = baseline_cpu / projected_cpu
        portable_incremental_projected_speedup = (
            process_local_projected_cpu / projected_cpu
        )
        for theorem in theorem_costs.values():
            theorem["projected_cpu_seconds"] += (
                overhead_budget_cpu_seconds_per_hit * theorem["cache_hits"]
            )

    theorem_rows = []
    for theorem_name in sorted(theorem_costs):
        values = theorem_costs[theorem_name]
        theorem_baseline = float(values["baseline_cpu_seconds"])
        process_local_cost = float(
            values["process_local_counterfactual_cpu_seconds"]
        )
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
                "ideal_portable_incremental_speedup": (
                    process_local_cost / ideal_cost
                    if process_local_cost > 0 and ideal_cost > 0
                    else None
                ),
                "projected_verifier_speedup": (
                    theorem_baseline / projected_cost
                    if theorem_baseline > 0
                    and projected_cost is not None
                    and projected_cost > 0
                    else None
                ),
                "projected_portable_incremental_speedup": (
                    process_local_cost / projected_cost
                    if process_local_cost > 0
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
    portable_incremental_speedups = sorted(
        float(row["projected_portable_incremental_speedup"])
        for row in theorem_rows
        if row["projected_portable_incremental_speedup"] is not None
    )
    portable_incremental_tails = {
        name: _quantile(portable_incremental_speedups, fraction)
        for name, fraction in (
            ("p10", 0.10),
            ("median", 0.50),
            ("p90", 0.90),
            ("p95", 0.95),
            ("p99", 0.99),
        )
    }

    maximum_total_overhead_for_target = max(
        0.0,
        process_local_projected_cpu / TARGET_VERIFIER_SPEEDUP
        - ideal_projected_cpu,
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

    local_pipeline_projection = None
    if pipeline_projection is not None:
        pipeline_cpu = float(pipeline_projection["baseline_cpu_seconds"])
        local_pipeline_projection = {
            "baseline_cpu_seconds": pipeline_cpu,
            "verifier_cpu_fraction": baseline_cpu / pipeline_cpu,
            "ideal_speedup": pipeline_cpu
            / (pipeline_cpu - baseline_cpu + local_ideal_projected_cpu),
            "projected_speedup": (
                pipeline_cpu
                / (pipeline_cpu - baseline_cpu + local_projected_cpu)
                if local_projected_cpu is not None
                else None
            ),
        }

    local_qualifying_theorems = {
        group["theorem_name"] for group in local_qualifying_groups
    }
    local_reusable_cpu_fraction = local_saved_cpu / baseline_cpu
    local_maximum_registered_overhead = (
        MAXIMUM_OVERHEAD_EQUIVALENT_PER_EIGHT_ATTEMPTS
        * local_qualifying_baseline_cpu
        / 8.0
    )
    local_maximum_total_overhead_for_target = max(
        0.0, baseline_cpu / TARGET_VERIFIER_SPEEDUP - local_ideal_projected_cpu
    )
    local_maximum_overhead_per_hit = (
        local_maximum_total_overhead_for_target / local_cache_hits
        if local_cache_hits
        else 0.0
    )
    local_criteria = {
        "has_qualifying_groups": bool(local_qualifying_groups),
        "group_coverage": (
            len(local_qualifying_groups) >= MINIMUM_QUALIFYING_GROUPS
        ),
        "theorem_coverage": (
            len(local_qualifying_theorems) >= MINIMUM_QUALIFYING_THEOREMS
        ),
        "reusable_cpu_fraction": (
            local_reusable_cpu_fraction
            >= MINIMUM_PROCESS_LOCAL_REUSABLE_CPU_FRACTION
        ),
        "registered_overhead_present": local_overhead_total is not None,
        "registered_overhead_within_limit": (
            local_overhead_total is not None
            and local_overhead_total <= local_maximum_registered_overhead
        ),
        "pipeline_cpu_present": local_pipeline_projection is not None,
        "pipeline_verifier_cpu_material": (
            pipeline_verifier_fraction is not None
            and pipeline_verifier_fraction >= MINIMUM_PIPELINE_VERIFIER_CPU_FRACTION
        ),
        "target_verifier_speedup": (
            local_projected_speedup is not None
            and local_projected_speedup >= TARGET_VERIFIER_SPEEDUP
        ),
    }
    if not local_criteria["has_qualifying_groups"]:
        local_decision = "stop_no_qualifying_process_local_groups"
    elif not local_criteria["group_coverage"] or not local_criteria["theorem_coverage"]:
        local_decision = "stop_insufficient_process_local_coverage"
    elif not local_criteria["reusable_cpu_fraction"]:
        local_decision = "stop_below_process_local_reusable_cpu_gate"
    elif not local_criteria["registered_overhead_present"]:
        local_decision = "inconclusive_missing_registered_overhead_budget"
    elif not local_criteria["registered_overhead_within_limit"]:
        local_decision = "stop_process_local_overhead_budget_exceeds_gate"
    elif not local_criteria["pipeline_cpu_present"]:
        local_decision = "inconclusive_missing_pipeline_cpu"
    elif not local_criteria["pipeline_verifier_cpu_material"]:
        local_decision = "stop_verifier_cpu_not_material_to_pipeline"
    elif not local_criteria["target_verifier_speedup"]:
        local_decision = "stop_below_target_process_local_speedup"
    else:
        local_decision = "read_only_process_local_value_gate_passed"

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
        "portable_incremental_cpu_fraction": portable_incremental_cpu_fraction
        >= MINIMUM_PORTABLE_INCREMENTAL_CPU_FRACTION,
        "registered_overhead_present": overhead_total is not None,
        "registered_overhead_within_limit": (
            overhead_total is not None and overhead_total <= maximum_registered_overhead
        ),
        "pipeline_cpu_present": pipeline_projection is not None,
        "pipeline_verifier_cpu_material": (
            pipeline_verifier_fraction is not None
            and pipeline_verifier_fraction >= MINIMUM_PIPELINE_VERIFIER_CPU_FRACTION
        ),
        "target_portable_incremental_speedup": (
            portable_incremental_projected_speedup is not None
            and portable_incremental_projected_speedup >= TARGET_VERIFIER_SPEEDUP
        ),
    }
    if not criteria["has_qualifying_groups"] and single_scope_groups:
        decision = "stop_no_cross_scope_exact_checkpoint_groups"
    elif not criteria["has_qualifying_groups"]:
        decision = "stop_no_qualifying_exact_checkpoint_groups"
    elif not criteria["group_coverage"] or not criteria["theorem_coverage"]:
        decision = "stop_insufficient_authentic_coverage"
    elif not criteria["portable_incremental_cpu_fraction"]:
        decision = "stop_below_portable_incremental_cpu_gate"
    elif not criteria["registered_overhead_present"]:
        decision = "inconclusive_missing_registered_overhead_budget"
    elif not criteria["registered_overhead_within_limit"]:
        decision = "stop_overhead_budget_exceeds_gate"
    elif not criteria["pipeline_cpu_present"]:
        decision = "inconclusive_missing_pipeline_cpu"
    elif not criteria["pipeline_verifier_cpu_material"]:
        decision = "stop_verifier_cpu_not_material_to_pipeline"
    elif not criteria["target_portable_incremental_speedup"]:
        decision = "stop_below_target_portable_incremental_speedup"
    else:
        decision = "read_only_value_gate_passed"

    if decision == "read_only_value_gate_passed":
        recommendation = "portable_checkpoint_candidate"
        recommendation_next_step = (
            "propose one bounded paired portable-checkpoint experiment under D-036"
        )
    elif local_decision == "read_only_process_local_value_gate_passed":
        recommendation = "process_local_prefix_reuse_candidate"
        recommendation_next_step = (
            "propose one bounded warm-baseline exact prefix-trie experiment under D-036"
        )
    elif decision.startswith("inconclusive_") or local_decision.startswith(
        "inconclusive_"
    ):
        recommendation = "inconclusive"
        recommendation_next_step = (
            "resolve missing authentic telemetry or a pre-registered overhead budget"
        )
    else:
        recommendation = "do_not_build_exact_checkpoint_reuse"
        recommendation_next_step = "do not run a SHRED implementation benchmark"

    return {
        "analysis": "authentic-checkpoint-trace-screen-v2",
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
            "minimum_execution_scopes_per_group": MINIMUM_EXECUTION_SCOPES,
            "target_verifier_speedup": TARGET_VERIFIER_SPEEDUP,
            "minimum_qualifying_groups": MINIMUM_QUALIFYING_GROUPS,
            "minimum_qualifying_theorems": MINIMUM_QUALIFYING_THEOREMS,
            "minimum_portable_incremental_cpu_fraction": (
                MINIMUM_PORTABLE_INCREMENTAL_CPU_FRACTION
            ),
            "minimum_process_local_reusable_cpu_fraction": (
                MINIMUM_PROCESS_LOCAL_REUSABLE_CPU_FRACTION
            ),
            "maximum_overhead_equivalent_per_eight_attempts": (
                MAXIMUM_OVERHEAD_EQUIVALENT_PER_EIGHT_ATTEMPTS
            ),
            "minimum_pipeline_verifier_cpu_fraction": (
                MINIMUM_PIPELINE_VERIFIER_CPU_FRACTION
            ),
            "portable_overhead_budget_cpu_seconds_per_hit": (
                overhead_budget_cpu_seconds_per_hit
            ),
            "portable_overhead_budget_source": overhead_budget_source,
            "process_local_overhead_budget_cpu_seconds_per_hit": (
                process_local_overhead_budget_cpu_seconds_per_hit
            ),
            "process_local_overhead_budget_source": (
                process_local_overhead_budget_source
            ),
        },
        "accounting": {
            "expected_attempts": expected_attempts,
            "physical_attempts": physical_records,
            "exact_checkpoint_attempts": sum(len(group) for group in groups.values()),
            "qualifying_exact_checkpoint_attempts": sum(
                group["attempts"] for group in qualifying_groups
            ),
            "insufficient_group_attempts": insufficient_attempts,
            "single_scope_exact_checkpoint_attempts": single_scope_attempts,
            "single_scope_exact_checkpoint_groups": single_scope_groups,
            "fallback_attempts": sum(fallback_reasons.values()),
            "fallback_reasons": dict(sorted(fallback_reasons.items())),
            "verdicts": dict(sorted(verdicts.items())),
            "qualifying_groups": len(qualifying_groups),
            "qualifying_theorems": len(qualifying_theorems),
            "cache_hits": cache_hits,
            "process_local_qualifying_attempts": sum(
                group["attempts"] for group in local_qualifying_groups
            ),
            "process_local_insufficient_group_attempts": (
                local_insufficient_attempts
            ),
            "process_local_qualifying_groups": len(local_qualifying_groups),
            "process_local_qualifying_theorems": len(local_qualifying_theorems),
            "process_local_cache_hits": local_cache_hits,
        },
        "process_local_verifier_cpu": {
            "baseline_seconds": baseline_cpu,
            "ideal_projected_seconds": local_ideal_projected_cpu,
            "ideal_saved_seconds": local_saved_cpu,
            "reusable_cpu_fraction": local_reusable_cpu_fraction,
            "ideal_speedup": local_ideal_speedup,
            "registered_overhead_seconds": local_overhead_total,
            "projected_seconds": local_projected_cpu,
            "projected_speedup": local_projected_speedup,
            "maximum_total_overhead_seconds_for_target": (
                local_maximum_total_overhead_for_target
            ),
            "maximum_overhead_seconds_per_hit_for_target": (
                local_maximum_overhead_per_hit
            ),
            "maximum_registered_overhead_seconds": (
                local_maximum_registered_overhead
            ),
            "claim_boundary": (
                "Exact prefix sharing inside one live Lean execution scope"
            ),
        },
        "process_local_replication_frontier": {
            "points": local_replication_frontier,
            "prefix_cost_model": (
                "For k replicas, charge min(sum observed prefix CPU, "
                "k * maximum observed prefix CPU) per qualifying group; "
                "cap replicas at that group's attempt count"
            ),
            "claim_boundary": (
                "Conservative CPU-only counterfactual from observed process CPU; "
                "no batch-latency claim without authentic wall-time and batch-boundary telemetry"
            ),
            "selection_rule": (
                "Pre-register a CPU or latency objective before execution; do not "
                "select k after a benchmark for the largest reported multiplier"
            ),
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
        "portable_incremental_verifier_cpu": {
            "process_local_counterfactual_seconds": process_local_projected_cpu,
            "process_local_saved_seconds": qualifying_process_local_saved_cpu,
            "incremental_saved_seconds": portable_incremental_saved_cpu,
            "incremental_saved_fraction_of_independent_baseline": (
                portable_incremental_cpu_fraction
            ),
            "ideal_projected_seconds": ideal_projected_cpu,
            "ideal_speedup_over_process_local": portable_incremental_ideal_speedup,
            "projected_seconds": projected_cpu,
            "projected_speedup_over_process_local": (
                portable_incremental_projected_speedup
            ),
            "claim_boundary": (
                "Incremental portable value after ideal process-local prefix sharing"
            ),
        },
        "within_single_execution_scope_only": {
            "groups": single_scope_groups,
            "attempts": single_scope_attempts,
            "baseline_cpu_seconds": single_scope_baseline_cpu,
            "ideal_saved_cpu_seconds": single_scope_ideal_saved_cpu,
            "claim_boundary": (
                "Process-local fan-out opportunity; excluded from the portable checkpoint gate"
            ),
        },
        "pipeline_cpu": pipeline_projection,
        "process_local_pipeline_cpu": local_pipeline_projection,
        "per_theorem_process_local_speedup_quantiles": local_tails,
        "per_theorem_process_local": local_theorem_rows,
        "process_local_qualifying_group_details": local_qualifying_groups,
        "per_theorem_speedup_quantiles": tails,
        "per_theorem_portable_incremental_speedup_quantiles": (
            portable_incremental_tails
        ),
        "per_theorem": theorem_rows,
        "qualifying_group_details": qualifying_groups,
        "process_local_gate": {
            "passes": (
                local_decision == "read_only_process_local_value_gate_passed"
            ),
            "decision": local_decision,
            "criteria": local_criteria,
            "next_step": (
                "propose one bounded warm-baseline exact prefix-trie experiment under D-036"
                if local_decision == "read_only_process_local_value_gate_passed"
                else "do not run a process-local SHRED implementation benchmark"
            ),
        },
        "recommendation": {
            "decision": recommendation,
            "next_step": recommendation_next_step,
        },
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


def seal_authentic_trace(
    output_manifest: Path,
    *,
    workload: dict[str, Any],
    partitions: list[Path],
) -> dict[str, Any]:
    """Freeze and validate producer-owned JSONL without modifying it.

    The producer must declare ``expected_attempts`` independently in workload
    metadata. Partition counts are observed while sealing and must match that
    declaration. The output is created without overwrite only after the same
    fail-closed validation used by the opportunity screener succeeds.
    """
    if not isinstance(workload, dict):
        raise AuthenticTraceError("workload metadata must be one JSON object")
    if "expected_attempts" not in workload:
        raise AuthenticTraceError(
            "workload metadata must independently declare expected_attempts"
        )
    if not partitions:
        raise AuthenticTraceError("at least one trace partition is required")

    output_manifest = output_manifest.resolve()
    if output_manifest.exists():
        raise AuthenticTraceError(f"refusing to overwrite manifest: {output_manifest}")

    resolved_partitions = [partition.resolve() for partition in partitions]
    if len(set(resolved_partitions)) != len(resolved_partitions):
        raise AuthenticTraceError("trace partitions must be unique")
    for partition in resolved_partitions:
        if not partition.is_file():
            raise AuthenticTraceError(f"missing trace partition: {partition}")
        if not (
            partition.name.endswith(".jsonl")
            or partition.name.endswith(".jsonl.gz")
        ):
            raise AuthenticTraceError(
                f"trace partition must end in .jsonl or .jsonl.gz: {partition}"
            )

    source_root = Path(
        os.path.commonpath([str(partition.parent) for partition in resolved_partitions])
    )
    partition_entries = []
    physical_attempts = 0
    for partition in resolved_partitions:
        records = sum(1 for _line_number, _record in _records(partition))
        physical_attempts += records
        partition_entries.append(
            {
                "path": str(partition.relative_to(source_root)),
                "sha256": _sha256(partition),
                "records": records,
            }
        )

    declared_attempts = workload.get("expected_attempts")
    if declared_attempts != physical_attempts:
        raise AuthenticTraceError(
            "producer-declared expected_attempts does not match physical records: "
            f"{declared_attempts!r} != {physical_attempts}"
        )

    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    source_root_default = os.path.relpath(source_root, output_manifest.parent)
    manifest = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "trace_kind": TRACE_KIND,
        "source_root_default": source_root_default,
        "workload": dict(workload),
        "telemetry": {
            "lineage_kind": "lean_native_exact_prefix",
            "cpu_clock": "process_cpu",
            "full_cpu_semantics": "warm_independent_complete_attempt",
            "prefix_cpu_semantics": "same_attempt_through_exact_checkpoint",
            "verdict_authority": "ordinary_lean",
        },
        "partitions": partition_entries,
    }
    try:
        rendered = json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"
    except (TypeError, ValueError) as error:
        raise AuthenticTraceError(
            f"workload metadata is not strict JSON: {error}"
        ) from error

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_manifest.parent,
            prefix=".shred-authentic-manifest-",
            suffix=".json",
            delete=False,
        ) as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
            temporary_path = Path(stream.name)
        validation = screen_authentic_trace(temporary_path)
        try:
            os.link(temporary_path, output_manifest)
        except FileExistsError as error:
            raise AuthenticTraceError(
                f"refusing to overwrite manifest: {output_manifest}"
            ) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return {
        "analysis": "authentic-checkpoint-trace-seal-v2",
        "evidence_label": "Validated immutable producer artifact",
        "claim_boundary": "Manifest sealing only; no Lean execution or speed claim",
        "manifest": str(output_manifest),
        "manifest_sha256": _sha256(output_manifest),
        "expected_attempts": physical_attempts,
        "partitions": partition_entries,
        "validation_decision": validation["gate"]["decision"],
    }
