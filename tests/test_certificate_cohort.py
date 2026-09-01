import gzip
import json
from pathlib import Path
import tempfile
import unittest

from lean_prefix.certificate_cohort import analyze_certificate_cohorts


class CertificateCohortTests(unittest.TestCase):
    def test_natural_exact_kind_can_pass_frozen_headline_gate(self):
        inputs = []
        results = []
        for index in range(128):
            proposal_id = f"p{index}"
            theorem = f"t{index % 10}"
            inputs.append(
                {
                    "proposal_id": proposal_id,
                    "units": [{"syntaxKind": "nlinarith"}],
                }
            )
            results.append(
                {
                    "proposal_id": proposal_id,
                    "theorem_name": theorem,
                    "stratum": "representative",
                    "baseline": {"complete": True, "cpu_seconds": 2.0},
                    "cached": {
                        "complete": True,
                        "cpu_seconds": 1.0,
                        "events": ([{"event": "hit"}] if index < 32 else []),
                    },
                }
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native_path = root / "inputs.jsonl.gz"
            result_path = root / "results.jsonl.gz"
            parent_path = root / "parent.json"
            with gzip.open(native_path, "wt", encoding="utf-8") as stream:
                for row in inputs:
                    stream.write(json.dumps(row) + "\n")
            with gzip.open(result_path, "wt", encoding="utf-8") as stream:
                for row in results:
                    stream.write(json.dumps(row) + "\n")
            parent_path.write_text(
                json.dumps(
                    {
                        "analysis": "closing-certificate-prevalence-summary-v1",
                        "strata": {
                            "representative": {"proposals": 128, "theorems": 10}
                        },
                        "provenance": {"hardware": ["fixture"]},
                    }
                ),
                encoding="utf-8",
            )
            report = analyze_certificate_cohorts(
                native_path,
                [result_path],
                parent_path,
                expected_representative_proposals=128,
                expected_representative_theorems=10,
            )
        self.assertEqual(
            report["decision"], "measured_natural_final_tactic_cohort_found"
        )
        self.assertEqual(report["accounting"]["passing_cohorts"], 1)
        cohort = report["passing_cohorts"][0]
        self.assertEqual(cohort["final_syntax_kind"], "nlinarith")
        self.assertEqual(cohort["automatic_hits"], 32)
        self.assertAlmostEqual(cohort["aggregate_cpu_speedup"], 2.0)
        self.assertAlmostEqual(cohort["per_theorem_cpu_speedup"]["p10"], 2.0)


if __name__ == "__main__":
    unittest.main()
