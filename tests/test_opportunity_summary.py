import gzip
import json
from pathlib import Path
import tempfile
import unittest

from lean_prefix.opportunity_summary import (
    OpportunitySummaryError,
    summarize_alternative_opportunities,
)


class OpportunitySummaryTests(unittest.TestCase):
    def _inputs(self, directory: str) -> tuple[Path, Path]:
        native = Path(directory) / "native.jsonl.gz"
        replay = Path(directory) / "replay.jsonl.gz"
        with gzip.open(native, "wt", encoding="utf-8") as stream:
            for proposal, proof in (("a", "same"), ("b", "same"), ("c", "other")):
                stream.write(json.dumps({
                    "proposal_id": proposal,
                    "proof_sha256": proof,
                }) + "\n")
        rows = [
            ("a", 10.0, 2.0, "shared"),
            ("b", 14.0, 4.0, "shared"),
            ("c", 6.0, 1.0, "other"),
        ]
        with gzip.open(replay, "wt", encoding="utf-8") as stream:
            for proposal, full_cpu, step_cpu, prefix in rows:
                stream.write(json.dumps({
                    "proposal_id": proposal,
                    "theorem_name": "t",
                    "replay_eligible": True,
                    "full": {
                        "complete": True,
                        "verdict_match": True,
                        "cpu_seconds": full_cpu,
                        "wall_seconds": full_cpu,
                    },
                    "profile": {"complete": True, "verdict_match": True},
                    "steps": [{
                        "reachability": "reached",
                        "prefix_sha256": prefix,
                        "edge_sha256": "edge",
                        "syntax_kind": "kind",
                        "cpu_seconds": step_cpu,
                    }],
                }) + "\n")
        return native, replay

    def test_separates_registered_and_unsafe_opportunities(self):
        with tempfile.TemporaryDirectory() as directory:
            native, replay = self._inputs(directory)
            report = summarize_alternative_opportunities(
                [replay], native, expected_proposals=3, bootstrap_samples=10
            )
            self.assertEqual(report["status"], "claim-valid")
            self.assertAlmostEqual(
                report["registered_exact_rooted_prefix"][
                    "fraction_of_full_cpu_mean_representative"
                ],
                0.1,
            )
            proof = report["exact_complete_proof_memoization"]
            self.assertAlmostEqual(
                proof["fraction_of_full_cpu_worst_observed_representative"],
                10.0 / 30.0,
            )
            edge = report["unsafe_upper_bounds"][
                "exact_tactic_edge_within_theorem_ignoring_state"
            ]
            self.assertGreater(
                edge["fraction_of_full_cpu_mean_representative"], 0.1
            )

    def test_disagreement_keeps_report_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            native, replay = self._inputs(directory)
            rows = []
            with gzip.open(replay, "rt", encoding="utf-8") as stream:
                rows = [json.loads(line) for line in stream]
            rows[0]["full"]["verdict_match"] = False
            with gzip.open(replay, "wt", encoding="utf-8") as stream:
                for row in rows:
                    stream.write(json.dumps(row) + "\n")
            report = summarize_alternative_opportunities(
                [replay], native, expected_proposals=3, bootstrap_samples=0
            )
            self.assertEqual(report["status"], "diagnostic-only")
            self.assertFalse(report["registered_exact_rooted_prefix"]["gate_passed"])

    def test_duplicate_replay_ids_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            native, replay = self._inputs(directory)
            with gzip.open(replay, "at", encoding="utf-8") as stream:
                stream.write(json.dumps({
                    "proposal_id": "a",
                    "theorem_name": "t",
                    "full": {},
                    "steps": [],
                }) + "\n")
            with self.assertRaises(OpportunitySummaryError):
                summarize_alternative_opportunities([replay], native)


if __name__ == "__main__":
    unittest.main()
