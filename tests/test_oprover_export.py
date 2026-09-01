import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from shred.oprover_export import (
    OProverExportError,
    export_saved_attempts,
    normalize_saved_attempt,
)
from lean_prefix.authentic_trace import seal_authentic_trace


DIGEST = "a" * 64


def captured_entry(proposal_id: str = "r1_p2_s0") -> dict:
    return {
        "global_step": 7,
        "proposal_id": proposal_id,
        "formal_statement": "theorem target : True := by sorry",
        "extracted_code": "import Mathlib\ntheorem target : True := by trivial",
        "success": True,
        "error_type": "none",
        "shred_cpu_capture": {
            "status": "captured",
            "group_id": "r1_p2",
            "group_index": 0,
            "group_size": 8,
            "repl_uuid": "fresh-repl-uuid",
            "cpu_boundaries": [
                "SHRED_CPU_BOUNDARY_V1\t0\t0\t0\t1\tparsing\t_anonymous",
                "SHRED_CPU_BOUNDARY_V1\t1\t1\t1\t4\tshred tactic execution@10:14\tKind.one",
                "SHRED_CPU_BOUNDARY_V1\t2\t1\t4\t7\tshred tactic execution@20:24\tKind.two",
                "SHRED_CPU_BOUNDARY_V1\t3\t0\t1\t10\telaboration\ttarget",
            ],
            "native_tactics": [
                {"startByte": 10, "endByte": 14, "syntaxKind": "Kind.one"},
                {"startByte": 20, "endByte": 24, "syntaxKind": "Kind.two"},
            ],
            "checkpoint": {
                "status": "captured",
                "prefix_length": 1,
                "prefix_edges_sha256": DIGEST,
                "parent_environment_sha256": DIGEST,
                "root_context_sha256": DIGEST,
                "checkpoint_artifact_sha256": DIGEST,
                "checkpoint_artifact_id": "artifact",
            },
        },
    }


class OProverExportTests(unittest.TestCase):
    def test_native_receipt_becomes_exact_checkpoint_record(self):
        record = normalize_saved_attempt(captured_entry(), "fixture:1")
        self.assertEqual(record["proposal_id"], "step7/r1_p2_s0")
        self.assertEqual(record["eligibility"], "exact_checkpoint")
        self.assertEqual(record["full_verifier_cpu_seconds"], 10 / 1_000_000_000)
        self.assertEqual(record["prefix_verifier_cpu_seconds"], 4 / 1_000_000_000)
        self.assertEqual(record["checkpoint_artifact_sha256"], DIGEST)
        self.assertEqual(
            record["verification_batch_sha256"],
            hashlib.sha256(
                b"oprover-verification-batch-v1\0" b"7\0" b"1"
            ).hexdigest(),
        )
        self.assertEqual(
            record["execution_scope_sha256"],
            hashlib.sha256(
                b"oprover-kimina-v1\0r1_p2\0fresh-repl-uuid"
            ).hexdigest(),
        )

    def test_export_counts_existing_exact_duplicate_without_reexecuting_it(self):
        cached = captured_entry("r1_p2_s1")
        cached["shred_cpu_capture"] = {
            "status": "cached_exact_duplicate",
            "representative_id": "r1_p2_s0",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "producer.jsonl"
            original = "".join(
                json.dumps(row) + "\n" for row in (captured_entry(), cached)
            )
            source.write_text(original, encoding="utf-8")
            output = root / "digest-only.jsonl"
            summary = export_saved_attempts([source], output, expected_attempts=2)

            self.assertEqual(summary["records"], 2)
            self.assertEqual(summary["exact_checkpoint"], 1)
            self.assertEqual(summary["cached_exact_duplicate"], 1)
            self.assertEqual(summary["batch_readiness"]["verification_batches"], 1)
            self.assertEqual(
                summary["batch_readiness"][
                    "process_local_groups_with_at_least_eight_exact_attempts"
                ],
                0,
            )
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(rows[1]["full_verifier_cpu_seconds"], 0.0)
            self.assertEqual(
                rows[1]["verification_batch_sha256"],
                rows[0]["verification_batch_sha256"],
            )
            self.assertEqual(rows[1]["eligibility"], "fallback")
            self.assertEqual(rows[1]["fallback_reason"], "existing_exact_duplicate_cache")

            with self.assertRaises(OProverExportError):
                export_saved_attempts([source], output, expected_attempts=2)

    def test_executed_attempt_without_process_cpu_fails_closed(self):
        row = captured_entry()
        row["shred_cpu_capture"] = {
            "status": "fallback",
            "fallback_reason": "group_transport_failure_no_retry",
        }
        with self.assertRaisesRegex(OProverExportError, "lacks exact process CPU"):
            normalize_saved_attempt(row, "fixture:1")

    def test_export_reports_digest_only_batch_group_readiness(self):
        rows = []
        for index in range(8):
            row = captured_entry(f"r1_p2_s{index}")
            row["shred_cpu_capture"]["group_index"] = index
            rows.append(row)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "producer.jsonl"
            source.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            output = root / "digest-only.jsonl"
            summary = export_saved_attempts([source], output, expected_attempts=8)
        readiness = summary["batch_readiness"]
        self.assertEqual(readiness["verification_batches"], 1)
        self.assertEqual(
            readiness["process_local_groups_with_at_least_eight_exact_attempts"],
            1,
        )
        self.assertEqual(readiness["maximum_exact_process_local_group_size"], 8)
        self.assertEqual(readiness["attempts_per_batch"]["minimum"], 8)
        self.assertEqual(
            readiness["qualifying_process_local_groups_per_batch"]["p10"], 1
        )

    def test_export_identifies_structurally_ready_pinned_batch(self):
        rows = []
        for group_index in range(44):
            group_digest = hashlib.sha256(f"group-{group_index}".encode()).hexdigest()
            for attempt_index in range(8):
                proposal_id = f"r1_p{group_index}_s{attempt_index}"
                row = captured_entry(proposal_id)
                capture = row["shred_cpu_capture"]
                capture["group_id"] = f"r1_p{group_index}"
                capture["group_index"] = attempt_index
                capture["repl_uuid"] = f"repl-{group_index}"
                capture["checkpoint"]["prefix_edges_sha256"] = group_digest
                capture["checkpoint"]["checkpoint_artifact_sha256"] = group_digest
                if group_index >= 38 and attempt_index > 0:
                    row["shred_cpu_capture"] = {
                        "status": "cached_exact_duplicate",
                        "representative_id": f"r1_p{group_index}_s0",
                    }
                rows.append(row)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "producer.jsonl"
            source.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            output = root / "digest-only.jsonl"
            summary = export_saved_attempts([source], output, expected_attempts=352)
        readiness = summary["batch_readiness"]
        candidate = readiness["pinned_oprover_8b_balanced_candidate"]
        self.assertEqual(
            readiness["process_local_groups_with_at_least_eight_exact_attempts"],
            38,
        )
        self.assertEqual(candidate["structurally_ready_batches"], 1)
        self.assertEqual(candidate["structurally_ready_batch_fraction"], 1.0)

    def test_exact_checkpoint_without_repl_scope_fails_closed(self):
        row = captured_entry()
        row["shred_cpu_capture"].pop("repl_uuid")
        with self.assertRaisesRegex(OProverExportError, "repl_uuid"):
            normalize_saved_attempt(row, "fixture:1")

    def test_exact_checkpoint_with_invalid_group_scope_fails_closed(self):
        row = captured_entry()
        row["shred_cpu_capture"]["group_index"] = 8
        with self.assertRaisesRegex(OProverExportError, "group_size"):
            normalize_saved_attempt(row, "fixture:1")

    def test_proposal_without_round_identity_fails_closed(self):
        row = captured_entry("unsupported")
        with self.assertRaisesRegex(OProverExportError, "verification batch"):
            normalize_saved_attempt(row, "fixture:1")

    def test_declared_count_mismatch_creates_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "producer.jsonl"
            source.write_text(json.dumps(captured_entry()) + "\n", encoding="utf-8")
            output = root / "digest-only.jsonl"
            with self.assertRaisesRegex(OProverExportError, "expected_attempts"):
                export_saved_attempts([source], output, expected_attempts=2)
            self.assertFalse(output.exists())

    def test_export_is_accepted_directly_by_no_overwrite_sealer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "producer.jsonl"
            source.write_text(json.dumps(captured_entry()) + "\n", encoding="utf-8")
            output = root / "digest-only.jsonl"
            export_saved_attempts([source], output, expected_attempts=1)
            manifest = root / "manifest.json"
            receipt = seal_authentic_trace(
                manifest,
                workload={
                    "name": "fixture",
                    "dataset_revision": "fixture-dataset",
                    "producer_git_commit": "fixture-producer",
                    "producer_git_dirty": False,
                    "producer_command": "fixture command",
                    "resolved_configuration_sha256": DIGEST,
                    "lean_revision": "v4.15.0",
                    "mathlib_revision": "fixture-mathlib",
                    "hardware": "fixture-cpu",
                    "concurrency": 1,
                    "timeout_seconds": 30,
                    "memory_limit_bytes": 1024,
                    "expected_attempts": 1,
                },
                partitions=[output],
            )
            self.assertEqual(receipt["expected_attempts"], 1)
            self.assertTrue(manifest.is_file())


if __name__ == "__main__":
    unittest.main()
