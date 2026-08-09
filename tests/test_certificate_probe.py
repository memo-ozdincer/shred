from pathlib import Path
import tempfile
import unittest

from lean_prefix.certificate_probe import (
    CertificateProbeError,
    summarize_certificate_probe,
)


class CertificateProbeTests(unittest.TestCase):
    def test_registered_pairs_are_aligned_and_unit_normalized(self):
        lines = [
            "tactic execution of nlinarith took 24.1s",
            "tactic execution of LeanPrefix.CertificateProbe.captureClosing took 1.21ms",
            "type checking took 6.73ms",
            "tactic execution of LeanPrefix.CertificateProbe.applyClosing took 2.23ms",
            "type checking took 71.8ms",
            "tactic execution of Mathlib.Tactic.Positivity.positivity took 19.3s",
            "tactic execution of LeanPrefix.CertificateProbe.captureClosing took 22ms",
            "type checking took 10ms",
            "tactic execution of LeanPrefix.CertificateProbe.applyClosing took 20.3ms",
            "type checking took 2ms",
            "wall_seconds=312.947 user_seconds=299.849 system_seconds=4.926",
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.log"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            report = summarize_certificate_probe(path, project_root=Path.cwd())
        self.assertEqual(len(report["benchmarks"]), 2)
        self.assertEqual(report["benchmarks"][0]["application_seconds"], 0.00223)

    def test_incomplete_profile_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.log"
            path.write_text("wall_seconds=1 user_seconds=1 system_seconds=0\n")
            with self.assertRaises(CertificateProbeError):
                summarize_certificate_probe(path)


if __name__ == "__main__":
    unittest.main()
