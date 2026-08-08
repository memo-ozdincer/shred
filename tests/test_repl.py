import unittest
from pathlib import Path
from unittest.mock import Mock

from lean_prefix.repl import LeanRepl, heartbeat_count, heartbeat_wrapper


class ReplProtocolTests(unittest.TestCase):
    def test_heartbeat_count_uses_numeric_info_message(self):
        response = {
            "messages": [
                {"severity": "warning", "data": "10"},
                {"severity": "info", "data": "not a count"},
                {"severity": "info", "data": " 5457 "},
            ]
        }
        self.assertEqual(heartbeat_count(response), 5457)

    def test_heartbeat_count_is_absent_on_failed_wrapper(self):
        self.assertIsNone(heartbeat_count({"message": "Lean error"}))

    def test_heartbeat_wrapper_preserves_relative_indentation(self):
        self.assertEqual(
            heartbeat_wrapper("have h := by\n  rfl"),
            "set_option maxHeartbeats 0 in\n"
            "  count_heartbeats\n"
            "    have h := by\n"
            "      rfl",
        )

    def test_proof_step_sends_theorem_declaration_name(self):
        client = LeanRepl(Path("."))
        client.request = Mock(return_value=None)
        client.proof_step(
            17,
            "exact h",
            count_heartbeats=False,
            decl_name="example_theorem",
        )
        client.request.assert_called_once_with({
            "proofState": 17,
            "tactic": "exact h",
            "declName": "example_theorem",
        })


if __name__ == "__main__":
    unittest.main()
