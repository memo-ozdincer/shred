import unittest

from lean_prefix.cli import _parser


class CliTests(unittest.TestCase):
    def test_authentic_trace_parses_distinct_overhead_budgets(self):
        args = _parser().parse_args(
            [
                "screen-authentic-trace",
                "--manifest",
                "manifest.json",
                "--output",
                "report.json",
                "--process-local-overhead-budget-cpu-seconds-per-hit",
                "0.002",
                "--process-local-overhead-budget-source",
                "local ceiling",
                "--portable-overhead-budget-cpu-seconds-per-hit",
                "0.01",
                "--portable-overhead-budget-source",
                "portable ceiling",
            ]
        )
        self.assertEqual(
            args.process_local_overhead_budget_cpu_seconds_per_hit, 0.002
        )
        self.assertEqual(args.process_local_overhead_budget_source, "local ceiling")
        self.assertEqual(args.portable_overhead_budget_cpu_seconds_per_hit, 0.01)
        self.assertEqual(args.portable_overhead_budget_source, "portable ceiling")

    def test_historical_overhead_flags_alias_only_portable_budget(self):
        args = _parser().parse_args(
            [
                "screen-authentic-trace",
                "--manifest",
                "manifest.json",
                "--output",
                "report.json",
                "--overhead-budget-cpu-seconds-per-hit",
                "0.01",
                "--overhead-budget-source",
                "historical portable ceiling",
            ]
        )
        self.assertEqual(args.portable_overhead_budget_cpu_seconds_per_hit, 0.01)
        self.assertEqual(
            args.portable_overhead_budget_source, "historical portable ceiling"
        )
        self.assertIsNone(args.process_local_overhead_budget_cpu_seconds_per_hit)
        self.assertIsNone(args.process_local_overhead_budget_source)


if __name__ == "__main__":
    unittest.main()
