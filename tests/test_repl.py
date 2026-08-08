import unittest

from lean_prefix.repl import heartbeat_count, heartbeat_wrapper


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
            "count_heartbeats\n  have h := by\n    rfl",
        )


if __name__ == "__main__":
    unittest.main()
