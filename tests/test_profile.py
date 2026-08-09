import unittest

from lean_prefix.profile import (
    ReplayProfileError,
    c0_verifier_declaration,
    in_process_reached_steps,
    lean_complete,
    theorem_root_code,
    theorem_root_outcome,
    unsupported_profile_syntax,
)


class ReplayProfileTests(unittest.TestCase):
    def test_completion_matches_verifier_policy(self):
        self.assertTrue(lean_complete({"env": 1}))
        self.assertFalse(lean_complete({"messages": [{"severity": "error", "data": "bad"}]}))
        self.assertFalse(lean_complete({"sorries": [{"goal": "False"}]}))

    def test_c0_fenced_code_contract_is_exact(self):
        statement = "theorem t : True := by\n"
        self.assertEqual(
            c0_verifier_declaration(statement, "  trivial\n```"),
            statement + "  trivial",
        )
        self.assertIsNone(c0_verifier_declaration(statement, "  trivial"))

    def test_in_process_profile_selects_direct_top_level_tactics(self):
        units = [
            {"syntaxKind": "Lean.Parser.Tactic.rintro"},
            {"syntaxKind": "Lean.Parser.Tactic.rwSeq"},
        ]
        stderr = "\n".join([
            "parsing took 2ms",
            "tactic execution of Lean.Parser.Tactic.rintro took 3ms",
            "simp took 5ms",
            "tactic execution of Lean.Parser.Tactic.rewriteSeq took 7ms",
            "tactic execution of Lean.Parser.Tactic.rwSeq took 11ms",
            "linting took 13ms",
        ])
        reached = in_process_reached_steps(units, stderr)
        self.assertEqual([step["tag"] for step in reached], [
            "Lean.Parser.Tactic.rintro",
            "Lean.Parser.Tactic.rwSeq",
        ])
        self.assertAlmostEqual(reached[0]["seconds"], 0.003)
        self.assertAlmostEqual(reached[1]["seconds"], 0.023)

    def test_in_process_profile_retains_only_reached_prefix(self):
        units = [
            {"syntaxKind": "Lean.Parser.Tactic.simp"},
            {"syntaxKind": "Lean.Parser.Tactic.exact"},
        ]
        stderr = "tactic execution of Lean.Parser.Tactic.simp took 400us\n"
        self.assertEqual(len(in_process_reached_steps(units, stderr)), 1)

    def test_in_process_profile_requires_ordered_top_level_alignment(self):
        units = [
            {"syntaxKind": "Lean.Parser.Tactic.simp"},
            {"syntaxKind": "Lean.Parser.Tactic.exact"},
        ]
        stderr = "\n".join([
            "tactic execution of Lean.Parser.Tactic.exact took 1ms",
            "tactic execution of Lean.Parser.Tactic.simp took 2ms",
        ])
        self.assertEqual(len(in_process_reached_steps(units, stderr)), 1)

    def test_in_process_profile_parses_units_and_ignores_other_stderr(self):
        units = [{"syntaxKind": "Lean.Parser.Tactic.simp"}]
        stderr = "\n".join([
            "warning: unrelated",
            "tactic execution of Lean.Parser.Tactic.simp took 250us",
            "another message took unknown",
        ])
        reached = in_process_reached_steps(units, stderr)
        self.assertEqual(len(reached), 1)
        self.assertAlmostEqual(reached[0]["seconds"], 0.00025)

    def test_in_process_profile_falls_back_on_ambiguous_duplicate_frames(self):
        units = [
            {"syntaxKind": "Lean.Parser.Tactic.simp"},
            {"syntaxKind": "Lean.Parser.Tactic.exact"},
        ]
        stderr = "\n".join([
            "tactic execution of Lean.Parser.Tactic.simp took 1ms",
            "tactic execution of Lean.Parser.Tactic.simp took 2ms",
            "tactic execution of Lean.Parser.Tactic.exact took 3ms",
        ])
        self.assertEqual(in_process_reached_steps(units, stderr), [])

    def test_root_placeholder_starts_on_a_new_indented_line(self):
        self.assertEqual(
            theorem_root_code("example : True := by\n"),
            "example : True := by\n  sorry",
        )
        self.assertEqual(
            theorem_root_code("example : True := by"),
            "example : True := by\n  sorry",
        )

    def test_root_outcome_accepts_exactly_one_snapshot(self):
        self.assertEqual(
            theorem_root_outcome("t", {"sorries": [{"proofState": 7}]}),
            (7, None),
        )

    def test_root_outcome_records_explicit_lean_rejection(self):
        error = {"severity": "error", "data": "undeclared identifier"}
        state, failure = theorem_root_outcome("t", {"messages": [error], "sorries": []})
        self.assertIsNone(state)
        self.assertEqual(failure, {
            "reason": "lean_rejected_theorem_root",
            "errors": [error],
        })

    def test_root_error_takes_precedence_over_a_sorry_snapshot(self):
        error = {"severity": "error", "data": "ambiguous declaration"}
        state, failure = theorem_root_outcome(
            "t", {"messages": [error], "sorries": [{"proofState": 7}]}
        )
        self.assertIsNone(state)
        self.assertEqual(failure, {
            "reason": "lean_rejected_theorem_root",
            "errors": [error],
        })

    def test_root_outcome_rejects_unexplained_missing_snapshot(self):
        with self.assertRaises(ReplayProfileError):
            theorem_root_outcome("t", {"sorries": []})

    def test_structural_sequences_are_not_standalone_tactics(self):
        units = [
            {"syntaxKind": "Lean.Parser.Tactic.simp"},
            {"syntaxKind": "Lean.cdot"},
            {"syntaxKind": "Lean.calcTactic"},
            {"syntaxKind": "Lean.Parser.Tactic.«tactic_<;>_»"},
            {"syntaxKind": "Mathlib.Tactic.induction'"},
        ]
        self.assertEqual(
            unsupported_profile_syntax(units),
            [
                "Lean.Parser.Tactic.«tactic_<;>_»",
                "Lean.calcTactic",
                "Lean.cdot",
                "Mathlib.Tactic.induction'",
            ],
        )

if __name__ == "__main__":
    unittest.main()
