import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from lean_prefix.authentic_trace import AuthenticTraceError, screen_authentic_trace


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


def exact_record(index: int, *, theorem: str = "t", group: str = "g") -> dict:
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
    }


def gate_records() -> list[dict]:
    records = []
    for theorem_index in range(10):
        theorem = f"t{theorem_index}"
        for group_index in range(10):
            group = f"{theorem}-{group_index}"
            for attempt_index in range(8):
                index = len(records)
                records.append(exact_record(index, theorem=theorem, group=group))
    return records


class AuthenticTraceTests(unittest.TestCase):
    def write_trace(self, root: Path, records: list[dict]) -> Path:
        partition = root / "trace.jsonl"
        partition.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        manifest = {
            "schema_version": 1,
            "trace_kind": "shred-authentic-checkpoint-trace-v1",
            "source_root_default": ".",
            "workload": {
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
            },
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
                overhead_budget_cpu_seconds_per_hit=0.1,
                overhead_budget_source="registered design ceiling",
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
        self.assertTrue(report["gate"]["passes"])
        self.assertGreater(report["pipeline_cpu"]["projected_speedup"], 1.5)

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


if __name__ == "__main__":
    unittest.main()
