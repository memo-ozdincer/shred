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


if __name__ == "__main__":
    unittest.main()
