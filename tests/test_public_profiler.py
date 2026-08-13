import unittest
import json
from pathlib import Path
import tempfile

from shred import create_manifest, recommend_profile


class PublicProfilerTests(unittest.TestCase):
    def test_manifest_initializer_registers_without_copying(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "rollouts.jsonl"
            source.write_text(
                "".join(
                    json.dumps(row) + "\n"
                    for row in (
                        {"theorem_name": "t", "proof": "by rfl", "correct": True},
                        {"theorem_name": "t", "proof": "by simp", "correct": False},
                    )
                ),
                encoding="utf-8",
            )
            manifest = create_manifest(
                [source], root / "workload.json", samples_per_theorem=2
            )
            self.assertEqual(manifest["expected"]["registered_proposals"], 2)
            self.assertEqual(source.read_text(encoding="utf-8").count("\n"), 2)

    def test_sample_never_becomes_deployment_evidence(self):
        recommendation = recommend_profile(
            {
                "status": "complete",
                "cpu_seconds": {
                    "opportunity_fraction_of_full_verification": 0.50,
                },
            },
            gate_fraction=0.15,
            screening=True,
        )
        self.assertEqual(recommendation["decision"], "screening_only")
        self.assertTrue(recommendation["passes_gate_on_sample"])

    def test_full_profile_enforces_registered_gate(self):
        recommendation = recommend_profile(
            {
                "status": "complete",
                "cpu_seconds": {
                    "opportunity_fraction_of_full_verification": 0.149,
                },
            },
            gate_fraction=0.15,
            screening=False,
        )
        self.assertEqual(
            recommendation["decision"], "do_not_deploy_exact_prefix_reuse"
        )

    def test_incomplete_profile_is_inconclusive(self):
        recommendation = recommend_profile(
            {"status": "invalid", "cpu_seconds": {}},
            gate_fraction=0.15,
            screening=False,
        )
        self.assertEqual(recommendation["decision"], "inconclusive")


if __name__ == "__main__":
    unittest.main()
