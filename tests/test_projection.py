import unittest

from lean_prefix.projection import (
    ProjectionError,
    projected_speedup,
    required_reusable_fraction,
)


class ProjectionTests(unittest.TestCase):
    def test_projection_uses_end_to_end_amdahl_model(self):
        result = projected_speedup(0.4, 20.0, 0.02)
        self.assertAlmostEqual(result["projected_cpu_fraction"], 0.64)
        self.assertAlmostEqual(result["projected_cpu_reduction_fraction"], 0.36)
        self.assertAlmostEqual(result["projected_throughput_multiplier"], 1.5625)

    def test_required_fraction_inverts_projection(self):
        fraction = required_reusable_fraction(2.0, 27.1, 0.02)
        result = projected_speedup(fraction, 27.1, 0.02)
        self.assertAlmostEqual(result["projected_throughput_multiplier"], 2.0)

    def test_impossible_target_fails_closed(self):
        with self.assertRaises(ProjectionError):
            required_reusable_fraction(100.0, 2.0, 0.02)


if __name__ == "__main__":
    unittest.main()
