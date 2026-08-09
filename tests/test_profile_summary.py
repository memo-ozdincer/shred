import gzip
import json
from pathlib import Path
import tempfile
import unittest

from lean_prefix.profile_summary import (
    ProfileSummaryError,
    _bootstrap_ratio,
    summarize_replay_profiles,
)


class ProfileSummaryTests(unittest.TestCase):
    def test_bootstrap_is_deterministic(self):
        pairs = [(1.0, 4.0), (2.0, 4.0)]
        self.assertEqual(
            _bootstrap_ratio(pairs, samples=100, seed=7),
            _bootstrap_ratio(pairs, samples=100, seed=7),
        )

    def test_empty_bootstrap_is_explicit(self):
        result = _bootstrap_ratio([], samples=10, seed=1)
        self.assertIsNone(result["low"])
        self.assertIsNone(result["high"])

    def test_cost_oracle_uses_one_mean_cost_per_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.jsonl.gz"
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                for index, cpu in enumerate((1.0, 3.0)):
                    stream.write(json.dumps({
                        "proposal_id": str(index),
                        "theorem_name": "t",
                        "native_unit_count": 1,
                        "native_eligible": True,
                        "sequential": {"complete": True, "verdict_match": True},
                        "full": {
                            "complete": True,
                            "verdict_match": True,
                            "cpu_seconds": 10.0,
                            "wall_seconds": 10.0,
                        },
                        "steps": [{
                            "prefix_sha256": "shared",
                            "mapped": True,
                            "reachability": "reached",
                            "cpu_seconds": cpu,
                            "wall_seconds": cpu,
                            "heartbeats": cpu * 1000,
                        }],
                    }) + "\n")
            report = summarize_replay_profiles(
                [path], expected_proposals=2, bootstrap_samples=10
            )
            self.assertEqual(report["cpu_seconds"]["reusable_prefix_opportunity"], 2.0)
            self.assertEqual(
                report["cpu_seconds"]["opportunity_fraction_of_full_verification"], 0.1
            )
            self.assertTrue(report["status"] == "complete")

    def test_duplicate_proposal_ids_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.jsonl"
            row = {"proposal_id": "same", "theorem_name": "t", "full": {}, "steps": []}
            path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")
            with self.assertRaises(ProfileSummaryError):
                summarize_replay_profiles([path])

    def test_invalid_theorem_root_is_explicit_zero_reached_work(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.jsonl"
            row = {
                "proposal_id": "invalid-root",
                "theorem_name": "bad",
                "native_unit_count": 2,
                "native_eligible": True,
                "full": {
                    "complete": False,
                    "verdict_match": True,
                    "cpu_seconds": 2.0,
                    "wall_seconds": 2.0,
                },
                "sequential": {
                    "complete": False,
                    "verdict_match": True,
                    "root_available": False,
                },
                "steps": [
                    {
                        "prefix_sha256": f"p{index}",
                        "reachability": "unreachable_invalid_root",
                    }
                    for index in range(2)
                ],
            }
            path.write_text(json.dumps(row) + "\n")
            report = summarize_replay_profiles([path], expected_proposals=1)
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["counts"]["root_unavailable"], 1)
            self.assertEqual(report["counts"]["native_reached_units"], 0)
            self.assertEqual(report["counts"]["unreachable_invalid_root"], 2)
            self.assertEqual(
                report["cpu_seconds"]["full_independent_verification"], 2.0
            )
            self.assertEqual(
                report["cpu_seconds"]["reusable_prefix_opportunity"], 0.0
            )

    def test_unknown_reachability_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.jsonl"
            row = {
                "proposal_id": "unknown",
                "theorem_name": "t",
                "native_eligible": True,
                "replay_eligible": True,
                "full": {"complete": False, "verdict_match": True},
                "sequential": {"complete": False, "verdict_match": True},
                "steps": [{"reachability": "mystery"}],
            }
            path.write_text(json.dumps(row) + "\n")
            with self.assertRaises(ProfileSummaryError):
                summarize_replay_profiles([path])

    def test_unreachable_completed_tail_is_not_counted_as_work(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.jsonl"
            row = {
                "proposal_id": "early-completion",
                "theorem_name": "t",
                "native_eligible": True,
                "replay_eligible": True,
                "native_unit_count": 2,
                "full": {
                    "complete": True,
                    "verdict_match": True,
                    "cpu_seconds": 2.0,
                    "wall_seconds": 2.0,
                },
                "sequential": {"complete": True, "verdict_match": True},
                "steps": [
                    {
                        "prefix_sha256": "done",
                        "reachability": "reached",
                        "cpu_seconds": 1.0,
                        "wall_seconds": 1.0,
                    },
                    {"reachability": "unreachable_after_completion"},
                ],
            }
            path.write_text(json.dumps(row) + "\n")
            report = summarize_replay_profiles([path], expected_proposals=1)
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["counts"]["native_reached_units"], 1)
            self.assertEqual(report["counts"]["unreachable_after_completion"], 1)

    def test_replay_fallback_retains_full_cost_but_excludes_prefix_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.jsonl"
            row = {
                "proposal_id": "fallback",
                "theorem_name": "t",
                "native_eligible": True,
                "replay_eligible": False,
                "native_unit_count": 1,
                "full": {
                    "complete": True,
                    "verdict_match": True,
                    "cpu_seconds": 3.0,
                    "wall_seconds": 4.0,
                },
                "sequential": {"supported": False},
                "steps": [{
                    "prefix_sha256": "must-not-count",
                    "reachability": "reached",
                    "cpu_seconds": 2.0,
                    "wall_seconds": 2.0,
                }],
            }
            path.write_text(json.dumps(row) + "\n")
            report = summarize_replay_profiles([path], expected_proposals=1)
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["counts"]["replay_fallback_proposals"], 1)
            self.assertEqual(report["cpu_seconds"]["full_independent_verification"], 3.0)
            self.assertEqual(report["cpu_seconds"]["profiled_reached_units"], 0)

    def test_full_timeout_is_an_accounted_negative_verdict_and_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.jsonl"
            row = {
                "proposal_id": "timeout",
                "theorem_name": "t",
                "native_eligible": True,
                "replay_eligible": False,
                "native_unit_count": 1,
                "full": {
                    "complete": False,
                    "verdict_match": True,
                    "timed_out": True,
                    "cpu_seconds": 299.0,
                    "wall_seconds": 300.0,
                },
                "sequential": {
                    "supported": False,
                    "not_attempted_reason": "full independent verification reached its timeout",
                },
                "steps": [],
            }
            path.write_text(json.dumps(row) + "\n")
            report = summarize_replay_profiles([path], expected_proposals=1)
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["counts"]["full_failures"], 0)
            self.assertEqual(report["counts"]["replay_fallback_proposals"], 1)
            self.assertEqual(
                report["cpu_seconds"]["full_independent_verification"], 299.0
            )
            self.assertEqual(
                report["cpu_seconds"]["reusable_prefix_opportunity"], 0.0
            )


if __name__ == "__main__":
    unittest.main()
