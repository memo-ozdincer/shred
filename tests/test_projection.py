import unittest

from lean_prefix.projection import (
    ProjectionError,
    affinity_schedule_projection,
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

    def test_oprover_8b_affinity_projection(self):
        result = affinity_schedule_projection(
            groups=44,
            attempts_per_group=8,
            verifier_slots=135,
            shared_prefix_cpu_fraction=0.8,
        )
        self.assertEqual(result["attempts"], 352)
        self.assertEqual(result["independent_batch_waves"], 3)
        self.assertEqual(result["affinity_group_waves"], 1)
        self.assertAlmostEqual(result["projected_cpu_throughput_multiplier"], 10 / 3)
        self.assertAlmostEqual(result["projected_batch_latency_multiplier"], 1.25)
        self.assertAlmostEqual(
            result[
                "minimum_shared_prefix_cpu_fraction_for_no_batch_latency_loss"
            ],
            5 / 7,
        )

    def test_oprover_32b_affinity_projection(self):
        result = affinity_schedule_projection(
            groups=336,
            attempts_per_group=4,
            verifier_slots=800,
            shared_prefix_cpu_fraction=0.8,
        )
        self.assertEqual(result["attempts"], 1344)
        self.assertEqual(result["independent_batch_waves"], 2)
        self.assertEqual(result["affinity_group_waves"], 1)
        self.assertAlmostEqual(result["projected_cpu_throughput_multiplier"], 2.5)
        self.assertAlmostEqual(result["projected_batch_latency_multiplier"], 1.25)
        self.assertAlmostEqual(
            result[
                "minimum_shared_prefix_cpu_fraction_for_no_batch_latency_loss"
            ],
            2 / 3,
        )

    def test_oprover_8b_replication_uses_spare_slots(self):
        result = affinity_schedule_projection(
            groups=44,
            attempts_per_group=8,
            verifier_slots=135,
            shared_prefix_cpu_fraction=0.8,
            replicas_per_group=3,
        )
        self.assertEqual(result["maximum_attempts_per_replica"], 3)
        self.assertEqual(result["affinity_replica_waves"], 1)
        self.assertAlmostEqual(result["projected_cpu_throughput_multiplier"], 2.0)
        self.assertAlmostEqual(
            result["projected_batch_latency_multiplier"], 15 / 7
        )
        self.assertEqual(
            result[
                "minimum_shared_prefix_cpu_fraction_for_no_batch_latency_loss"
            ],
            0.0,
        )
        self.assertAlmostEqual(
            result["maximum_overhead_fraction_per_reuse_for_two_x_cpu"], 0.0
        )

    def test_two_replicas_have_balanced_overhead_headroom(self):
        result = affinity_schedule_projection(
            groups=44,
            attempts_per_group=8,
            verifier_slots=135,
            shared_prefix_cpu_fraction=0.8,
            replicas_per_group=2,
        )
        self.assertEqual(result["maximum_attempts_per_replica"], 4)
        self.assertAlmostEqual(result["projected_cpu_throughput_multiplier"], 2.5)
        self.assertAlmostEqual(
            result["projected_batch_latency_multiplier"], 1.875
        )
        self.assertAlmostEqual(
            result["maximum_overhead_fraction_per_reuse_for_two_x_cpu"], 2 / 15
        )
        self.assertAlmostEqual(
            result[
                "maximum_overhead_fraction_per_reuse_for_one_point_five_x_batch_latency"
            ],
            2 / 15,
        )

        with_two_percent_overhead = affinity_schedule_projection(
            groups=44,
            attempts_per_group=8,
            verifier_slots=135,
            shared_prefix_cpu_fraction=0.8,
            replicas_per_group=2,
            overhead_cpu_fraction_per_reuse=0.02,
        )
        self.assertAlmostEqual(
            with_two_percent_overhead["projected_cpu_throughput_multiplier"],
            8 / 3.32,
        )
        self.assertAlmostEqual(
            with_two_percent_overhead["projected_batch_latency_multiplier"],
            3 / 1.66,
        )
        impossible_latency = affinity_schedule_projection(
            groups=44,
            attempts_per_group=8,
            verifier_slots=135,
            shared_prefix_cpu_fraction=0.8,
            overhead_cpu_fraction_per_reuse=0.5,
        )
        self.assertIsNone(
            impossible_latency[
                "minimum_shared_prefix_cpu_fraction_for_no_batch_latency_loss"
            ]
        )
        self.assertIsNone(
            impossible_latency[
                "maximum_overhead_fraction_per_reuse_for_one_point_five_x_batch_latency"
            ]
        )

    def test_oprover_32b_replication_uses_spare_slots(self):
        result = affinity_schedule_projection(
            groups=336,
            attempts_per_group=4,
            verifier_slots=800,
            shared_prefix_cpu_fraction=0.8,
            replicas_per_group=2,
        )
        self.assertEqual(result["maximum_attempts_per_replica"], 2)
        self.assertEqual(result["affinity_replica_waves"], 1)
        self.assertAlmostEqual(
            result["projected_cpu_throughput_multiplier"], 5 / 3
        )
        self.assertAlmostEqual(
            result["projected_batch_latency_multiplier"], 5 / 3
        )

    def test_affinity_projection_rejects_invalid_topology(self):
        for kwargs in (
            {
                "groups": 0,
                "attempts_per_group": 8,
                "verifier_slots": 135,
                "shared_prefix_cpu_fraction": 0.8,
            },
            {
                "groups": 44,
                "attempts_per_group": 1,
                "verifier_slots": 135,
                "shared_prefix_cpu_fraction": 0.8,
            },
            {
                "groups": 44,
                "attempts_per_group": 8,
                "verifier_slots": 135,
                "shared_prefix_cpu_fraction": 1.1,
            },
            {
                "groups": 44,
                "attempts_per_group": 8,
                "verifier_slots": 135,
                "shared_prefix_cpu_fraction": 0.8,
                "replicas_per_group": 9,
            },
            {
                "groups": 44,
                "attempts_per_group": 8,
                "verifier_slots": 135,
                "shared_prefix_cpu_fraction": True,
            },
            {
                "groups": 44,
                "attempts_per_group": 8,
                "verifier_slots": 135,
                "shared_prefix_cpu_fraction": 0.8,
                "overhead_cpu_fraction_per_reuse": True,
            },
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ProjectionError):
                affinity_schedule_projection(**kwargs)


if __name__ == "__main__":
    unittest.main()
