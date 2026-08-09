import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from lean_prefix.certificate_prevalence import (
    CERTIFICATE_CONTEXT,
    select_certificate_prevalence_theorems,
    summarize_certificate_prevalence,
    wrap_final_tactic,
)


class CertificatePrevalenceTests(unittest.TestCase):
    def test_repl_context_imports_and_opens_the_certificate_tactic(self):
        self.assertIn("import LeanPrefix.AutomaticCertificate", CERTIFICATE_CONTEXT)
        self.assertIn("open LeanPrefix.AutomaticCertificate", CERTIFICATE_CONTEXT)

    def test_final_native_tactic_is_wrapped_without_heuristic_splitting(self):
        proof = "by\n  ring_nf\n  nlinarith"
        wrapped = wrap_final_tactic(
            proof,
            [{"startByte": 15, "stopByte": 24, "text": "nlinarith"}],
        )
        self.assertEqual(
            wrapped,
            "by\n  ring_nf\n  reuse_closing in\n    nlinarith",
        )

    def test_selection_strata_are_deterministic_and_disjoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.jsonl.gz"
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                for theorem_index in range(20):
                    for candidate_index in range(2):
                        stream.write(json.dumps({
                            "proposal_id": f"{theorem_index}-{candidate_index}",
                            "theorem_name": f"theorem_{theorem_index:02d}",
                            "full": {"complete": True},
                            "steps": [{
                                "depth": 1,
                                "edge_sha256": f"edge-{theorem_index}",
                                "reachability": "reached",
                                "cpu_seconds": float(theorem_index + 1),
                            }],
                        }) + "\n")
            first = select_certificate_prevalence_theorems(
                [path], representative_count=5, enriched_count=3
            )
            second = select_certificate_prevalence_theorems(
                [path], representative_count=5, enriched_count=3
            )
        representative = {item["theorem_name"] for item in first["representative"]}
        enriched = {item["theorem_name"] for item in first["enriched"]}
        self.assertFalse(representative & enriched)
        self.assertEqual(first["representative"], second["representative"])
        self.assertEqual(first["enriched"], second["enriched"])

    def test_summary_gate_fails_on_a_verdict_disagreement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "result.jsonl.gz"
            with gzip.open(artifact, "wt", encoding="utf-8") as stream:
                stream.write(json.dumps({
                    "stratum": "representative",
                    "proposal_id": "p0",
                    "theorem_name": "t0",
                    "candidate_index": 0,
                    "baseline": {
                        "complete": False, "cpu_seconds": 1.0, "timed_out": False,
                        "process_error": None,
                    },
                    "cached": {
                        "complete": True, "cpu_seconds": 0.1, "timed_out": False,
                        "process_error": None, "instrumented": True,
                        "events": [{"event": "hit"}],
                    },
                }) + "\n")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            report = root / "report.json"
            report.write_text(json.dumps({"artifact": {"sha256": digest}}), encoding="utf-8")
            summary = summarize_certificate_prevalence([artifact], [report])
        self.assertEqual(summary["decision_gate"]["outcome"], "stop_or_redirect")
        self.assertEqual(
            len(summary["strata"]["representative"]["verdict_disagreements"]), 1
        )


if __name__ == "__main__":
    unittest.main()
