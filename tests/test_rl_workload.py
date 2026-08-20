import gzip
import json
from pathlib import Path
import tempfile
import unittest

from lean_prefix.rl_workload import select_rl_workload, summarize_report


def _record(theorem, index, full_cpu, final_cpu, edge="same", complete=True):
    return {
        "theorem_name": theorem,
        "candidate_index": index,
        "full": {"complete": complete, "cpu_seconds": full_cpu},
        "steps": ([{
            "depth": 1,
            "reachability": "reached",
            "cpu_seconds": final_cpu,
            "edge_sha256": edge,
            "syntax_kind": "nlinarith",
        }] if complete else []),
    }


class RlWorkloadTests(unittest.TestCase):
    def test_admission_uses_conservative_repeated_final_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.jsonl.gz"
            rows = [
                _record("admitted", index, 1.0, 0.75)
                for index in range(32)
            ] + [
                _record("control", index, 1.0, 0.1, edge=str(index))
                for index in range(32)
            ]
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")
            report = select_rl_workload(
                [path], conservative_acceleration=27.0
            )
        admitted = report["admitted"]
        self.assertEqual(admitted["theorems"], 1)
        self.assertEqual(admitted["next_rollout_proposals"], 32)
        self.assertAlmostEqual(admitted["conservative_reusable_cpu_seconds"], 23.25)
        self.assertEqual(admitted["theorems_detail"][0]["theorem_name"], "admitted")

    def test_missing_cpu_prevents_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.jsonl.gz"
            rows = [_record("missing", index, 1.0, 0.75) for index in range(32)]
            rows[0]["full"]["cpu_seconds"] = None
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")
            report = select_rl_workload(
                [path], conservative_acceleration=27.0
            )
        self.assertEqual(report["admitted"]["theorems"], 0)

    def test_summary_retains_digests_but_drops_names(self):
        report = {
            "analysis": "example",
            "admitted": {"theorem_names_sha256": "a", "theorems_detail": [1]},
            "control": {"theorem_names_sha256": "b", "theorem_names": ["x"]},
        }
        summary = summarize_report(report)
        self.assertEqual(summary["analysis"], "example-summary")
        self.assertNotIn("theorems_detail", summary["admitted"])
        self.assertNotIn("theorem_names", summary["control"])
        self.assertEqual(summary["admitted"]["theorem_names_sha256"], "a")


if __name__ == "__main__":
    unittest.main()
