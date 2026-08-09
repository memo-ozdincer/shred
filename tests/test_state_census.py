import gzip
import hashlib
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
                        "candidate_index": index,
                        "full": {"complete": True},
                        "alignment": {"status": "aligned"},
                        "steps": [{
                            "depth": 1,
                            "prefix_sha256": prefix,
                            "edge_sha256": "edge",
                            "visible_goal_sha256": "goal",
                            "syntax_kind": "nlinarith",
                            "tactic_text": "nlinarith",
                            "visible_goal": "x : Nat ⊢ x = x",
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
            capture_report = Path(directory) / "capture.json"
            capture_report.write_text(json.dumps({
                "analysis": "authentic-visible-state-census-v1",
                "theorem_name": "t",
                "artifact": {
                    "sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
                },
                "configuration": {
                    "all_tactics": True,
                    "restart_every_proposals": 1,
                },
                "revisions": {
                    "project_git": {"commit": "a", "dirty": False},
                    "lean_workspace_git": {"commit": "b", "dirty": True},
                },
                "hardware": {"hostname": "test"},
                "counts": {
                    "selected_proposals": 2,
                    "completed": 2,
                    "aligned": 2,
                    "fallbacks": 0,
                    "timeouts": 0,
                    "errors": 0,
                },
                "timing": {"wall_seconds": 1.0},
            }), encoding="utf-8")
            report = summarize_visible_state_census(
                [state], [replay], [capture_report]
            )
            self.assertEqual(report["counts"]["reconvergent_groups"], 1)
            self.assertEqual(report["counts"]["verdict_comparisons"], 2)
            self.assertEqual(report["cpu_seconds"]["exact_prefix_saved"], 0.0)
            self.assertEqual(report["cpu_seconds"]["visible_state_edge_saved"], 3.0)
            closing = report["closing_tactic_diagnostic"]
            self.assertEqual(closing["counts"]["occurrences"], 2)
            self.assertEqual(closing["cpu_seconds"]["visible_state_edge_saved"], 3.0)
            self.assertEqual(report["top_reconvergent_groups"][0]["distinct_prefixes"], 2)
            self.assertEqual(report["capture_provenance"]["counts"]["errors"], 0)


if __name__ == "__main__":
    unittest.main()
