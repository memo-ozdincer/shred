import unittest

from lean_prefix.external_repair import (
    ExternalRepairError,
    common_prefix_bytes,
    lean_nontrivia_bytes,
    source_position_speedup,
)


class ExternalRepairTests(unittest.TestCase):
    def test_common_prefix_uses_exact_utf8_bytes(self):
        left = "by\n  exact café\n".encode()
        right = "by\n  exact case\n".encode()
        self.assertEqual(common_prefix_bytes(left, right), len("by\n  exact ca".encode()))

    def test_source_position_sensitivity_has_explicit_overhead(self):
        self.assertAlmostEqual(source_position_speedup(3, 0.5), 3 / 2.06)
        self.assertAlmostEqual(source_position_speedup(16, 0.8), 16 / 4.32)

    def test_source_position_sensitivity_rejects_invalid_inputs(self):
        with self.assertRaises(ExternalRepairError):
            source_position_speedup(0, 0.5)
        with self.assertRaises(ExternalRepairError):
            source_position_speedup(2, 1.1)

    def test_nontrivia_counter_ignores_nested_and_line_comments(self):
        source = b'by /- outer /- inner -/ end -/ exact "a -- b" -- tail\n rfl'
        self.assertEqual(
            lean_nontrivia_bytes(source),
            len(b'byexact"a -- b"rfl'),
        )


if __name__ == "__main__":
    unittest.main()
