import gzip
import json
from pathlib import Path
import tempfile
import unittest

from lean_prefix.state_census import (
    ordered_tactic_alignment,
    summarize_visible_state_census,
)


class StateCensusTests(unittest.TestCase):
    def test_alignment_requires_one_exact_ordered_path(self):
        self.assertEqual(
            ordered_tactic_alignment(["rw [h]", "ring"], ["rw [h]", "ring"]),
            ("unique", [0, 1]),
        )
        self.assertEqual(
            ordered_tactic_alignment(["ring"], ["ring", "ring"]),
            ("ambiguous", []),
        )
        self.assertEqual(
            ordered_tactic_alignment(["omega"], ["ring"]),
            ("absent", []),
        )

    def test_visible_state_summary_measures_reconvergence_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.jsonl.gz"
            replay = Path(directory) / "replay.jsonl.gz"
            with gzip.open(state, "wt", encoding="utf-8") as stream:
                for index, prefix in enumerate(("p1", "p2")):
                    stream.write(json.dumps({
                        "proposal_id": str(index),
                        "theorem_name": "t",
                        "full": {"complete": True},
                        "alignment": {"status": "aligned"},
                        "steps": [{
                            "depth": 1,
                            "prefix_sha256": prefix,
                            "edge_sha256": "edge",
                            "visible_goal_sha256": "goal",
                            "syntax_kind": "nlinarith",
                        }],
                    }) + "\n")
            with gzip.open(replay, "wt", encoding="utf-8") as stream:
                for index, prefix, cpu in ((0, "p1", 2.0), (1, "p2", 4.0)):
                    stream.write(json.dumps({
                        "proposal_id": str(index),
                        "full": {"complete": True, "cpu_seconds": 10.0},
                        "steps": [{
                            "depth": 1,
                            "prefix_sha256": prefix,
                            "edge_sha256": "edge",
                            "reachability": "reached",
                            "cpu_seconds": cpu,
                        }],
                    }) + "\n")
            report = summarize_visible_state_census([state], [replay])
            self.assertEqual(report["counts"]["reconvergent_groups"], 1)
            self.assertEqual(report["cpu_seconds"]["exact_prefix_saved"], 0.0)
            self.assertEqual(report["cpu_seconds"]["visible_state_edge_saved"], 3.0)


if __name__ == "__main__":
    unittest.main()
