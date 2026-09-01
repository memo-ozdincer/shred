import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from lean_prefix.authentic_trace import (
    AuthenticTraceError,
    screen_authentic_trace,
    seal_authentic_trace,
)


DIGESTS = {
    name: hashlib.sha256(name.encode()).hexdigest()
    for name in (
        "config",
        "proposal",
        "statement",
        "environment",
        "context",
        "prefix",
        "checkpoint",
        "other-checkpoint",
    )
}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def exact_record(
    index: int, *, theorem: str = "t", group: str = "g", scope: str | None = None
) -> dict:
    return {
        "proposal_id": f"p{index}",
        "proposal_sha256": digest(f"proposal-{index}"),
        "theorem_name": theorem,
        "theorem_statement_sha256": digest(f"statement-{theorem}"),
        "verdict": "accepted" if index % 2 == 0 else "rejected",
        "full_verifier_cpu_seconds": 10.0,
        "eligibility": "exact_checkpoint",
        "prefix_verifier_cpu_seconds": 8.0,
        "parent_environment_sha256": DIGESTS["environment"],
        "root_context_sha256": digest(f"context-{theorem}"),
        "prefix_edges_sha256": digest(f"prefix-{group}"),
        "checkpoint_artifact_sha256": digest(f"checkpoint-{group}"),
        "execution_scope_sha256": digest(scope or f"scope-{index // 4}"),
    }


def gate_records() -> list[dict]:
    records = []
    for theorem_index in range(10):
        theorem = f"t{theorem_index}"
        for group_index in range(10):
            group = f"{theorem}-{group_index}"
            for attempt_index in range(8):
                index = len(records)
                records.append(
                    exact_record(
                        index,
                        theorem=theorem,
                        group=group,
                        scope=f"scope-{group}-{attempt_index}",
                    )
                )
    return records


def process_local_gate_records() -> list[dict]:
    records = []
    for theorem_index in range(10):
        theorem = f"t{theorem_index}"
        for group_index in range(10):
            group = f"{theorem}-{group_index}"
            for _attempt_index in range(8):
                index = len(records)
                records.append(
                    exact_record(
                        index,
                        theorem=theorem,
                        group=group,
                        scope=f"one-live-scope-{group}",
                    )
                )
    return records


class AuthenticTraceTests(unittest.TestCase):
    def workload_metadata(self, records: list[dict]) -> dict:
        return {
            "name": "existing-run",
            "dataset_revision": "dataset-commit",
            "producer_git_commit": "producer-commit",
            "producer_git_dirty": False,
            "producer_command": "run-existing-workload --frozen",
            "resolved_configuration_sha256": DIGESTS["config"],
            "lean_revision": "v4.test",
            "mathlib_revision": "mathlib-commit",
            "hardware": "test cpu",
            "concurrency": 1,
            "timeout_seconds": 30.0,
            "memory_limit_bytes": 1024,
            "expected_attempts": len(records),
            "pipeline_total_cpu_seconds": sum(
                record["full_verifier_cpu_seconds"] for record in records
            )
            * 2,
        }

    def write_trace(self, root: Path, records: list[dict]) -> Path:
        partition = root / "trace.jsonl"
        partition.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        manifest = {
            "schema_version": 2,
            "trace_kind": "shred-authentic-checkpoint-trace-v2",
            "source_root_default": ".",
            "workload": self.workload_metadata(records),
            "telemetry": {
                "lineage_kind": "lean_native_exact_prefix",
                "cpu_clock": "process_cpu",
                "full_cpu_semantics": "warm_independent_complete_attempt",
                "prefix_cpu_semantics": "same_attempt_through_exact_checkpoint",
                "verdict_authority": "ordinary_lean",
            },
            "partitions": [
                {
                    "path": partition.name,
                    "sha256": hashlib.sha256(partition.read_bytes()).hexdigest(),
                    "records": len(records),
                }
            ],
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path

    def test_frozen_authentic_coverage_passes_two_x_gate_with_overhead_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), gate_records())
            report = screen_authentic_trace(
                manifest,
                portable_overhead_budget_cpu_seconds_per_hit=0.1,
                portable_overhead_budget_source="registered portable design ceiling",
            )
        self.assertEqual(report["accounting"]["physical_attempts"], 800)
        self.assertEqual(report["accounting"]["cache_hits"], 700)
        self.assertEqual(
            report["accounting"]["verdicts"],
            {"accepted": 400, "rejected": 400},
        )
        self.assertAlmostEqual(report["verifier_cpu"]["baseline_seconds"], 8000.0)
        self.assertAlmostEqual(
            report["verifier_cpu"]["ideal_projected_seconds"], 2400.0
        )
        self.assertAlmostEqual(report["verifier_cpu"]["projected_seconds"], 2470.0)
        self.assertGreater(report["verifier_cpu"]["projected_speedup"], 3.0)
        self.assertEqual(
            report["portable_incremental_verifier_cpu"][
                "process_local_saved_seconds"
            ],
            0.0,
        )
        self.assertGreater(
            report["portable_incremental_verifier_cpu"][
                "projected_speedup_over_process_local"
            ],
            3.0,
        )
        self.assertGreater(
            report["per_theorem_portable_incremental_speedup_quantiles"][
                "median"
            ],
            3.0,
        )
        self.assertTrue(report["gate"]["passes"])
        self.assertFalse(report["process_local_gate"]["passes"])
        self.assertEqual(
            report["process_local_gate"]["decision"],
            "stop_no_qualifying_process_local_groups",
        )
        self.assertEqual(
            report["recommendation"]["decision"],
            "portable_checkpoint_candidate",
        )
        self.assertGreater(report["pipeline_cpu"]["projected_speedup"], 1.5)

    def test_process_local_gate_can_pass_without_portable_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), process_local_gate_records())
            report = screen_authentic_trace(
                manifest,
                process_local_overhead_budget_cpu_seconds_per_hit=0.1,
                process_local_overhead_budget_source="registered local design ceiling",
            )
        self.assertTrue(report["process_local_gate"]["passes"])
        self.assertEqual(
            report["process_local_gate"]["decision"],
            "read_only_process_local_value_gate_passed",
        )
        self.assertFalse(report["gate"]["passes"])
        self.assertEqual(
            report["gate"]["decision"],
            "stop_no_cross_scope_exact_checkpoint_groups",
        )
        self.assertEqual(
            report["recommendation"]["decision"],
            "process_local_prefix_reuse_candidate",
        )
        self.assertGreater(
            report["process_local_verifier_cpu"]["projected_speedup"], 3.0
        )
        self.assertGreater(
            report["per_theorem_process_local_speedup_quantiles"]["median"], 3.0
        )
        frontier = report["process_local_replication_frontier"]
        self.assertEqual(len(frontier["points"]), 8)
        one_replica = frontier["points"][0]
        self.assertEqual(one_replica["replicas_per_group"], 1)
        self.assertEqual(
            one_replica["reused_attempts"],
            report["accounting"]["process_local_cache_hits"],
        )
        self.assertAlmostEqual(
            one_replica["ideal_projected_cpu_seconds"],
            report["process_local_verifier_cpu"]["ideal_projected_seconds"],
        )
        self.assertAlmostEqual(
            one_replica["projected_cpu_speedup"],
            report["process_local_verifier_cpu"]["projected_speedup"],
        )
        three_replicas = frontier["points"][2]
        self.assertAlmostEqual(three_replicas["ideal_cpu_speedup"], 2.0)
        eight_replicas = frontier["points"][-1]
        self.assertEqual(eight_replicas["reused_attempts"], 0)
        self.assertAlmostEqual(eight_replicas["ideal_cpu_speedup"], 1.0)
        self.assertAlmostEqual(eight_replicas["projected_cpu_speedup"], 1.0)

    def test_process_local_gate_requires_registered_overhead(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), process_local_gate_records())
            report = screen_authentic_trace(manifest)
        self.assertEqual(
            report["process_local_gate"]["decision"],
            "inconclusive_missing_registered_overhead_budget",
        )
        self.assertEqual(report["recommendation"]["decision"], "inconclusive")

    def test_replication_frontier_charges_observed_prefix_variation_conservatively(self):
        records = [
            exact_record(index, group="variable", scope="one-scope")
            for index in range(8)
        ]
        for index, record in enumerate(records, start=1):
            record["prefix_verifier_cpu_seconds"] = float(index)
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), records)
            report = screen_authentic_trace(
                manifest,
                process_local_overhead_budget_cpu_seconds_per_hit=0.0,
                process_local_overhead_budget_source="zero-overhead ceiling",
            )
        points = report["process_local_replication_frontier"]["points"]
        self.assertAlmostEqual(
            points[0]["conservative_replicated_prefix_cpu_seconds"], 8.0
        )
        self.assertAlmostEqual(
            points[1]["conservative_replicated_prefix_cpu_seconds"], 16.0
        )
        self.assertAlmostEqual(points[1]["conservative_saved_cpu_seconds"], 20.0)
        self.assertAlmostEqual(points[-1]["ideal_cpu_speedup"], 1.0)

    def test_real_cost_service_schedule_reproduces_oprover_8b_topology(self):
        records = []
        for group_index in range(44):
            for _attempt_index in range(8):
                index = len(records)
                records.append(
                    exact_record(
                        index,
                        theorem=f"t{group_index % 10}",
                        group=f"g{group_index}",
                        scope=f"scope-g{group_index}",
                    )
                )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.write_trace(root, records)
            manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
            manifest_value["workload"]["verifier_slots"] = 135
            manifest.write_text(json.dumps(manifest_value), encoding="utf-8")
            report = screen_authentic_trace(
                manifest,
                process_local_overhead_budget_cpu_seconds_per_hit=0.0,
                process_local_overhead_budget_source="zero-overhead ceiling",
            )
        frontier = report["process_local_replication_frontier"]
        self.assertAlmostEqual(
            frontier["independent_lpt_cpu_service_makespan_seconds"], 30.0
        )
        one_replica = frontier["points"][0]
        self.assertAlmostEqual(
            one_replica["projected_cpu_service_makespan_seconds"], 24.0
        )
        self.assertAlmostEqual(
            one_replica["projected_cpu_service_makespan_speedup"], 1.25
        )
        three_replicas = frontier["points"][2]
        self.assertAlmostEqual(three_replicas["projected_cpu_speedup"], 2.0)
        self.assertAlmostEqual(
            three_replicas["projected_cpu_service_makespan_seconds"], 14.0
        )
        self.assertAlmostEqual(
            three_replicas["projected_cpu_service_makespan_speedup"], 30.0 / 14.0
        )

    def test_verifier_slots_must_be_a_positive_integer(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), [exact_record(0)])
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["workload"]["verifier_slots"] = True
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(AuthenticTraceError, "verifier_slots"):
                screen_authentic_trace(manifest)

    def test_portable_budget_does_not_authorize_process_local_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), process_local_gate_records())
            report = screen_authentic_trace(
                manifest,
                overhead_budget_cpu_seconds_per_hit=0.1,
                overhead_budget_source="portable-only ceiling",
            )
        self.assertEqual(
            report["process_local_gate"]["decision"],
            "inconclusive_missing_registered_overhead_budget",
        )

    def test_process_local_budget_does_not_authorize_portable_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), gate_records())
            report = screen_authentic_trace(
                manifest,
                process_local_overhead_budget_cpu_seconds_per_hit=0.1,
                process_local_overhead_budget_source="local-only ceiling",
            )
        self.assertEqual(
            report["gate"]["decision"],
            "inconclusive_missing_registered_overhead_budget",
        )

    def test_process_local_budget_requires_source(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), process_local_gate_records())
            with self.assertRaisesRegex(
                AuthenticTraceError, "process-local overhead budget and its source"
            ):
                screen_authentic_trace(
                    manifest,
                    process_local_overhead_budget_cpu_seconds_per_hit=0.1,
                )

    def test_portable_budget_aliases_cannot_be_mixed(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), gate_records())
            with self.assertRaisesRegex(
                AuthenticTraceError,
                "either portable overhead arguments or their historical aliases",
            ):
                screen_authentic_trace(
                    manifest,
                    overhead_budget_cpu_seconds_per_hit=0.1,
                    overhead_budget_source="historical",
                    portable_overhead_budget_cpu_seconds_per_hit=0.1,
                    portable_overhead_budget_source="current",
                )

    def test_boolean_overhead_budgets_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), gate_records())
            with self.assertRaisesRegex(AuthenticTraceError, "must be non-negative"):
                screen_authentic_trace(
                    manifest,
                    portable_overhead_budget_cpu_seconds_per_hit=True,
                    portable_overhead_budget_source="invalid",
                )
            with self.assertRaisesRegex(
                AuthenticTraceError, "process-local overhead budget must be non-negative"
            ):
                screen_authentic_trace(
                    manifest,
                    process_local_overhead_budget_cpu_seconds_per_hit=True,
                    process_local_overhead_budget_source="invalid",
                )

    def test_process_local_gate_rejects_excessive_overhead(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), process_local_gate_records())
            report = screen_authentic_trace(
                manifest,
                process_local_overhead_budget_cpu_seconds_per_hit=1.0,
                process_local_overhead_budget_source="measured local upper bound",
            )
        self.assertEqual(
            report["process_local_gate"]["decision"],
            "stop_process_local_overhead_budget_exceeds_gate",
        )

    def test_small_group_is_counted_but_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(
                Path(directory), [exact_record(index) for index in range(7)]
            )
            report = screen_authentic_trace(
                manifest,
                overhead_budget_cpu_seconds_per_hit=0.0,
                overhead_budget_source="zero-overhead ceiling",
            )
        self.assertEqual(report["accounting"]["insufficient_group_attempts"], 7)
        self.assertEqual(
            report["gate"]["decision"],
            "stop_no_qualifying_exact_checkpoint_groups",
        )

    def test_single_execution_scope_cannot_pass_portable_gate(self):
        records = [
            exact_record(index, scope="one-live-repl") for index in range(8)
        ]
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), records)
            report = screen_authentic_trace(
                manifest,
                overhead_budget_cpu_seconds_per_hit=0.0,
                overhead_budget_source="zero-overhead ceiling",
            )
        self.assertEqual(
            report["accounting"]["single_scope_exact_checkpoint_attempts"], 8
        )
        self.assertEqual(
            report["accounting"]["single_scope_exact_checkpoint_groups"], 1
        )
        self.assertEqual(
            report["gate"]["decision"],
            "stop_no_cross_scope_exact_checkpoint_groups",
        )
        self.assertEqual(
            report["within_single_execution_scope_only"]["ideal_saved_cpu_seconds"],
            56.0,
        )

    def test_within_scope_saving_cannot_masquerade_as_portable_value(self):
        records = gate_records()
        for group_index in range(100):
            for offset in range(8):
                records[group_index * 8 + offset]["execution_scope_sha256"] = digest(
                    f"mixed-scope-{group_index}-{offset // 4}"
                )
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), records)
            report = screen_authentic_trace(
                manifest,
                overhead_budget_cpu_seconds_per_hit=0.0,
                overhead_budget_source="zero-overhead ceiling",
            )
        self.assertAlmostEqual(report["verifier_cpu"]["ideal_speedup"], 10 / 3)
        incremental = report["portable_incremental_verifier_cpu"]
        self.assertEqual(incremental["process_local_saved_seconds"], 4800.0)
        self.assertEqual(incremental["incremental_saved_seconds"], 800.0)
        self.assertAlmostEqual(
            incremental["projected_speedup_over_process_local"], 4 / 3
        )
        self.assertEqual(
            report["gate"]["decision"],
            "stop_below_portable_incremental_cpu_gate",
        )
        self.assertEqual(
            report["process_local_gate"]["decision"],
            "stop_no_qualifying_process_local_groups",
        )
        self.assertFalse(
            report["gate"]["criteria"]["portable_incremental_cpu_fraction"]
        )

    def test_exact_checkpoint_requires_execution_scope_identity(self):
        record = exact_record(0)
        record.pop("execution_scope_sha256")
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), [record])
            with self.assertRaisesRegex(
                AuthenticTraceError, "execution_scope_sha256"
            ):
                screen_authentic_trace(manifest)

    def test_version_one_draft_cannot_pass_version_two_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = self.write_trace(root, [exact_record(0)])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["schema_version"] = 1
            manifest["trace_kind"] = "shred-authentic-checkpoint-trace-v1"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                AuthenticTraceError, "unexpected authentic trace manifest identity"
            ):
                screen_authentic_trace(manifest_path)

    def test_default_gate_rejects_too_narrow_authentic_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(
                Path(directory), [exact_record(index) for index in range(8)]
            )
            report = screen_authentic_trace(
                manifest,
                overhead_budget_cpu_seconds_per_hit=0.1,
                overhead_budget_source="registered design ceiling",
            )
        self.assertFalse(report["gate"]["passes"])
        self.assertEqual(
            report["gate"]["decision"], "stop_insufficient_authentic_coverage"
        )
        self.assertFalse(report["gate"]["criteria"]["group_coverage"])

    def test_excessive_registered_overhead_fails_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), gate_records())
            report = screen_authentic_trace(
                manifest,
                overhead_budget_cpu_seconds_per_hit=1.0,
                overhead_budget_source="measured loader ceiling",
            )
        self.assertEqual(
            report["gate"]["decision"], "stop_overhead_budget_exceeds_gate"
        )
        self.assertFalse(
            report["gate"]["criteria"]["registered_overhead_within_limit"]
        )

    def test_textual_lineage_declaration_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = self.write_trace(
                root, [exact_record(index) for index in range(8)]
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["telemetry"]["lineage_kind"] = "textual_common_prefix"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(AuthenticTraceError, "lineage_kind"):
                screen_authentic_trace(manifest_path)

    def test_unrecognized_manifest_fields_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = self.write_trace(root, [exact_record(0)])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["projection_override"] = 100.0
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(AuthenticTraceError, "unexpected.*fields"):
                screen_authentic_trace(manifest_path)

    def test_missing_overhead_budget_stays_inconclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), gate_records())
            report = screen_authentic_trace(manifest)
        self.assertFalse(report["gate"]["passes"])
        self.assertEqual(
            report["gate"]["decision"],
            "inconclusive_missing_registered_overhead_budget",
        )
        self.assertIsNone(report["verifier_cpu"]["projected_speedup"])

    def test_fallback_is_explicit_and_receives_no_saving(self):
        records = gate_records()
        records.append(
            {
                "proposal_id": "fallback",
                "proposal_sha256": DIGESTS["proposal"],
                "theorem_name": "u",
                "theorem_statement_sha256": DIGESTS["statement"],
                "verdict": "timed_out",
                "full_verifier_cpu_seconds": 20.0,
                "eligibility": "fallback",
                "fallback_reason": "missing_native_checkpoint",
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), records)
            report = screen_authentic_trace(
                manifest,
                overhead_budget_cpu_seconds_per_hit=0.1,
                overhead_budget_source="registered design ceiling",
            )
        self.assertEqual(report["accounting"]["fallback_attempts"], 1)
        self.assertEqual(
            report["accounting"]["fallback_reasons"],
            {"missing_native_checkpoint": 1},
        )
        self.assertEqual(report["accounting"]["verdicts"]["timed_out"], 1)

    def test_checkpoint_digest_cannot_hide_conflicting_identity(self):
        records = [exact_record(index) for index in range(8)]
        records[-1]["root_context_sha256"] = DIGESTS["other-checkpoint"]
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), records)
            with self.assertRaisesRegex(AuthenticTraceError, "conflicting exact identity"):
                screen_authentic_trace(manifest)

    def test_partition_checksum_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.write_trace(root, [exact_record(index) for index in range(8)])
            (root / "trace.jsonl").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(AuthenticTraceError, "checksum mismatch"):
                screen_authentic_trace(manifest)

    def test_non_finite_cpu_fails_closed(self):
        records = [exact_record(index) for index in range(8)]
        records[0]["full_verifier_cpu_seconds"] = float("nan")
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_trace(Path(directory), records)
            with self.assertRaisesRegex(AuthenticTraceError, "full_verifier_cpu"):
                screen_authentic_trace(manifest)

    def test_partition_cannot_escape_source_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            manifest_path = self.write_trace(source, [exact_record(0)])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            partition = source / "trace.jsonl"
            outside = root / "outside.jsonl"
            partition.replace(outside)
            manifest["partitions"][0]["path"] = "../outside.jsonl"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(AuthenticTraceError, "escapes source root"):
                screen_authentic_trace(manifest_path)

    def test_seal_freezes_and_validates_without_changing_partition(self):
        records = gate_records()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            partition = root / "producer.jsonl"
            partition.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            original_bytes = partition.read_bytes()
            output = root / "sealed" / "manifest.json"
            receipt = seal_authentic_trace(
                output,
                workload=self.workload_metadata(records),
                partitions=[partition],
            )
            report = screen_authentic_trace(output)
            sealed = json.loads(output.read_text(encoding="utf-8"))
            after_bytes = partition.read_bytes()
        self.assertEqual(after_bytes, original_bytes)
        self.assertEqual(receipt["expected_attempts"], 800)
        self.assertEqual(
            receipt["validation_decision"],
            "inconclusive_missing_registered_overhead_budget",
        )
        self.assertEqual(
            sealed["telemetry"]["lineage_kind"], "lean_native_exact_prefix"
        )
        self.assertEqual(report["accounting"]["physical_attempts"], 800)

    def test_seal_requires_independent_attempt_count_and_creates_no_output(self):
        records = [exact_record(index) for index in range(8)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            partition = root / "producer.jsonl"
            partition.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            output = root / "manifest.json"
            workload = self.workload_metadata(records)
            workload["expected_attempts"] = 9
            with self.assertRaisesRegex(
                AuthenticTraceError, "does not match physical records"
            ):
                seal_authentic_trace(
                    output,
                    workload=workload,
                    partitions=[partition],
                )
            self.assertFalse(output.exists())

    def test_seal_refuses_overwrite(self):
        records = [exact_record(index) for index in range(8)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            partition = root / "producer.jsonl"
            partition.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            output = root / "manifest.json"
            output.write_text("owned by producer\n", encoding="utf-8")
            with self.assertRaisesRegex(AuthenticTraceError, "refusing to overwrite"):
                seal_authentic_trace(
                    output,
                    workload=self.workload_metadata(records),
                    partitions=[partition],
                )
            self.assertEqual(output.read_text(encoding="utf-8"), "owned by producer\n")


if __name__ == "__main__":
    unittest.main()
