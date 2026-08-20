import unittest

from lean_prefix.retention_gate import summarize_retention, theorem_bootstrap


class RetentionGateTests(unittest.TestCase):
    def test_gate_fails_when_upper_bootstrap_bound_is_below_requirement(self):
        admission = [{
            "theorem_name": "t",
            "baseline_cpu_seconds": 32.0,
            "conservative_reusable_cpu_seconds": 16.0,
            "conservative_reusable_cpu_fraction": 0.5,
        }]
        records = [{
            "theorem_name": "t",
            "baseline": {"complete": True, "cpu_seconds": 1.0},
            "cached": {
                "complete": True,
                "cpu_seconds": 0.9,
                "events": [{"event": "hit"}],
            },
        } for _ in range(32)]
        report = summarize_retention(
            admission, records, conservative_acceleration=27.051195461299475
        )
        self.assertFalse(report["gate"]["passes"])
        self.assertTrue(report["gate"]["decisive_failure"])
        self.assertEqual(
            report["gate"]["decision"],
            "stop_no_new_c1_lean_or_cluster_compute",
        )
        self.assertEqual(report["overlap"]["automatic_hits"], 32)
        self.assertEqual(report["overlap"]["verdict_disagreements"], 0)

    def test_bootstrap_is_deterministic(self):
        pairs = [(10.0, 8.0), (20.0, 15.0), (5.0, 5.1)]
        self.assertEqual(
            theorem_bootstrap(pairs, samples=100, seed=7),
            theorem_bootstrap(pairs, samples=100, seed=7),
        )


if __name__ == "__main__":
    unittest.main()
