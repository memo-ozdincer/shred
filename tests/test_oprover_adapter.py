import unittest

from shred.oprover_adapter import (
    OProverAdapterError,
    split_boundary_stderr,
    summarize_cpu_boundaries,
)


LOG = """warning: retained verbatim
SHRED_CPU_BOUNDARY_V1\t3\t2\t1200000000\t1500000000\tshred tactic execution@10:20\tLean.Parser.Tactic.simp
SHRED_CPU_BOUNDARY_V1\t1\t0\t1000000000\t1100000000\tparsing\t_anonymous
SHRED_CPU_BOUNDARY_V1\t4\t2\t1500000000\t1900000000\tshred tactic execution@21:30\tLean.Parser.Tactic.linarith
SHRED_CPU_BOUNDARY_V1\t2\t0\t1100000000\t2000000000\telaboration\t_anonymous
real error retained"""


class OProverAdapterTests(unittest.TestCase):
    def test_exact_ranges_produce_cumulative_prefix_cpu(self):
        records, remainder = split_boundary_stderr(LOG)
        report = summarize_cpu_boundaries(
            records,
            [
                {
                    "startByte": 10,
                    "endByte": 20,
                    "syntaxKind": "Lean.Parser.Tactic.simp",
                },
                {
                    "start_byte": 21,
                    "end_byte": 30,
                    "syntax_kind": "Lean.Parser.Tactic.linarith",
                },
            ],
        )
        self.assertEqual(remainder, "warning: retained verbatim\nreal error retained")
        self.assertAlmostEqual(report["full_verifier_cpu_seconds"], 1.0)
        self.assertAlmostEqual(
            report["native_tactics"][0]["prefix_verifier_cpu_seconds"], 0.5
        )
        self.assertAlmostEqual(
            report["native_tactics"][1]["prefix_verifier_cpu_seconds"], 0.9
        )

    def test_duplicate_exact_range_fails_closed(self):
        records, _ = split_boundary_stderr(
            LOG
            + "\nSHRED_CPU_BOUNDARY_V1\t5\t3\t1300000000\t1400000000"
            + "\tshred tactic execution@10:20\tLean.Parser.Tactic.simp"
        )
        with self.assertRaisesRegex(OProverAdapterError, "2 CPU boundary matches"):
            summarize_cpu_boundaries(
                records,
                [{
                    "start_byte": 10,
                    "end_byte": 20,
                    "syntax_kind": "Lean.Parser.Tactic.simp",
                }],
            )

    def test_missing_command_boundary_fails_closed(self):
        records, _ = split_boundary_stderr(
            "SHRED_CPU_BOUNDARY_V1\t1\t0\t1\t2\tparsing\t_anonymous"
        )
        with self.assertRaisesRegex(OProverAdapterError, "at least one"):
            summarize_cpu_boundaries(records, [])

    def test_multiple_commands_form_one_exact_request_envelope(self):
        records, _ = split_boundary_stderr(
            "\n".join(
                [
                    "SHRED_CPU_BOUNDARY_V1\t1\t0\t100\t110\tparsing\t_anonymous",
                    "SHRED_CPU_BOUNDARY_V1\t2\t0\t110\t120\telaboration\t_anonymous",
                    "SHRED_CPU_BOUNDARY_V1\t3\t0\t120\t130\tparsing\t_anonymous",
                    "SHRED_CPU_BOUNDARY_V1\t5\t1\t140\t170\tshred tactic execution@10:20\tLean.Parser.Tactic.simp",
                    "SHRED_CPU_BOUNDARY_V1\t4\t0\t130\t180\telaboration\t_anonymous",
                ]
            )
        )
        report = summarize_cpu_boundaries(
            records,
            [{
                "startByte": 10,
                "endByte": 20,
                "syntaxKind": "Lean.Parser.Tactic.simp",
            }],
        )
        self.assertEqual(report["parsing_boundaries"], 2)
        self.assertEqual(report["elaboration_boundaries"], 2)
        self.assertAlmostEqual(report["full_verifier_cpu_seconds"], 80e-9)

    def test_malformed_boundary_is_not_silently_treated_as_stderr(self):
        with self.assertRaisesRegex(OProverAdapterError, "malformed"):
            split_boundary_stderr("SHRED_CPU_BOUNDARY_V1\t1\t2")

    def test_native_text_without_byte_range_is_never_aligned(self):
        records, _ = split_boundary_stderr(LOG)
        with self.assertRaisesRegex(OProverAdapterError, "lacks exact byte range"):
            summarize_cpu_boundaries(records, [{"tactic": "simp"}])

    def test_syntax_kind_must_also_match(self):
        records, _ = split_boundary_stderr(LOG)
        with self.assertRaisesRegex(OProverAdapterError, "syntax kind conflicts"):
            summarize_cpu_boundaries(
                records,
                [{
                    "start_byte": 10,
                    "end_byte": 20,
                    "syntax_kind": "Lean.Parser.Tactic.rfl",
                }],
            )


if __name__ == "__main__":
    unittest.main()
