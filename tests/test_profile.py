import unittest

from lean_prefix.profile import (
    ReplayProfileError,
    heartbeat_instrumentation_supported,
    lean_complete,
    proof_step_succeeded,
    requires_runtime_fallback,
    theorem_root_code,
    theorem_root_outcome,
    unsupported_standalone_syntax,
)


class ReplayProfileTests(unittest.TestCase):
    def test_completion_matches_verifier_policy(self):
        self.assertTrue(lean_complete({"env": 1}))
        self.assertFalse(lean_complete({"messages": [{"severity": "error", "data": "bad"}]}))
        self.assertFalse(lean_complete({"sorries": [{"goal": "False"}]}))

    def test_root_placeholder_starts_on_a_new_indented_line(self):
        self.assertEqual(theorem_root_code("example : True := by\n"), "example : True := by\n  sorry")
        self.assertEqual(theorem_root_code("example : True := by"), "example : True := by\n  sorry")

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

    def test_step_with_error_message_never_succeeds(self):
        response = {
            "proofState": 1,
            "goals": [],
            "messages": [{"severity": "error", "data": "bad tactic"}],
        }
        self.assertFalse(proof_step_succeeded(response))
        self.assertTrue(proof_step_succeeded({"proofState": 1, "goals": []}))

    def test_auxiliary_declaration_limitation_requires_fallback(self):
        response = {
            "messages": [{
                "severity": "error",
                "data": (
                    "auxiliary declaration cannot be created when declaration "
                    "name is not available"
                ),
            }],
        }
        self.assertTrue(requires_runtime_fallback(response))
        self.assertFalse(requires_runtime_fallback({"messages": []}))

    def test_structural_sequences_are_not_standalone_tactics(self):
        units = [
            {"syntaxKind": "Lean.Parser.Tactic.simp"},
            {"syntaxKind": "Lean.cdot"},
            {"syntaxKind": "Lean.calcTactic"},
        ]
        self.assertEqual(
            unsupported_standalone_syntax(units),
            ["Lean.calcTactic", "Lean.cdot"],
        )

    def test_semicolon_sequence_skips_heartbeat_wrapper(self):
        self.assertFalse(
            heartbeat_instrumentation_supported("Lean.Parser.Tactic.«tactic_<;>_»")
        )
        self.assertTrue(
            heartbeat_instrumentation_supported("Lean.Parser.Tactic.exact")
        )

if __name__ == "__main__":
    unittest.main()
