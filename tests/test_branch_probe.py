import unittest

from lean_prefix.branch_probe import BranchProbeError, _quantiles, summarize_timings


class BranchProbeTests(unittest.TestCase):
    def test_summarize_timings_reports_exact_fork_speedup(self):
        shared_prefix = {"wall_seconds": 6.0, "cpu_seconds": 6.0}
        suffixes = [{"wall_seconds": 4.0, "cpu_seconds": 4.0}] * 8
        prefixes = [{"wall_seconds": 6.0, "cpu_seconds": 6.0}] * 8
        summary = summarize_timings(shared_prefix, suffixes, prefixes, suffixes)
        self.assertEqual(summary["branches"], 8)
        self.assertAlmostEqual(summary["wall"]["independent_prefix_fraction"], 0.6)
        self.assertAlmostEqual(summary["wall"]["measured_speedup"], 80 / 38)

    def test_summarize_timings_requires_one_prefix_per_suffix(self):
        metric = {"wall_seconds": 1.0, "cpu_seconds": 1.0}
        with self.assertRaises(BranchProbeError):
            summarize_timings(metric, [metric], [], [metric])

    def test_summarize_timings_preserves_missing_cpu(self):
        shared = {"wall_seconds": 1.0, "cpu_seconds": None}
        suffix = {"wall_seconds": 1.0, "cpu_seconds": None}
        summary = summarize_timings(shared, [suffix], [suffix], [suffix])
        self.assertIsNone(summary["cpu"])

    def test_quantiles_report_required_tail_points(self):
        records = [{"wall_seconds": float(value)} for value in range(1, 11)]
        summary = _quantiles(records, "wall_seconds")
        self.assertEqual(
            summary,
            {
                "minimum": 1.0,
                "median": 5.0,
                "p90": 9.0,
                "p95": 9.0,
                "p99": 9.0,
                "maximum": 10.0,
            },
        )


if __name__ == "__main__":
    unittest.main()
