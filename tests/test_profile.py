import unittest

from lean_prefix.profile import (
    ReplayProfileError,
    lean_complete,
    theorem_root_code,
    theorem_root_outcome,
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

    def test_root_outcome_rejects_unexplained_missing_snapshot(self):
        with self.assertRaises(ReplayProfileError):
            theorem_root_outcome("t", {"sorries": []})

if __name__ == "__main__":
    unittest.main()
