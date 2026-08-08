import unittest

from lean_prefix.prefix import summarize_prefixes


class PrefixSummaryTests(unittest.TestCase):
    def test_shared_nodes_are_counted_once(self) -> None:
        summary = summarize_prefixes(
            [
                ("simp", "ring"),
                ("simp", "nlinarith"),
                ("norm_num",),
            ]
        )
        self.assertEqual(summary.proposals, 3)
        self.assertEqual(summary.independent_steps, 5)
        self.assertEqual(summary.unique_nodes, 4)
        self.assertEqual(summary.reusable_step_occurrences, 1)
        self.assertEqual(summary.oracle_ratio, 1.25)

    def test_empty_sequences_have_defined_ratio(self) -> None:
        summary = summarize_prefixes([(), ()])
        self.assertEqual(summary.proposals, 2)
        self.assertEqual(summary.independent_steps, 0)
        self.assertEqual(summary.unique_nodes, 0)
        self.assertEqual(summary.oracle_ratio, 1.0)


if __name__ == "__main__":
    unittest.main()

