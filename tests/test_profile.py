import unittest

from lean_prefix.profile import lean_complete, theorem_root_code


class ReplayProfileTests(unittest.TestCase):
    def test_completion_matches_verifier_policy(self):
        self.assertTrue(lean_complete({"env": 1}))
        self.assertFalse(lean_complete({"messages": [{"severity": "error", "data": "bad"}]}))
        self.assertFalse(lean_complete({"sorries": [{"goal": "False"}]}))

    def test_root_placeholder_starts_on_a_new_indented_line(self):
        self.assertEqual(theorem_root_code("example : True := by\n"), "example : True := by\n  sorry")
        self.assertEqual(theorem_root_code("example : True := by"), "example : True := by\n  sorry")

if __name__ == "__main__":
    unittest.main()
