import unittest
import os
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from lean_prefix.repl import (
    LeanRepl,
    ReplTimeout,
    _proc_cpu_seconds,
    heartbeat_count,
    heartbeat_wrapper,
)


class ReplProtocolTests(unittest.TestCase):
    def test_linux_process_cpu_clock_is_available(self):
        value = _proc_cpu_seconds(os.getpid())
        self.assertIsNotNone(value)
        self.assertGreaterEqual(value, 0.0)

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

    def test_timeout_retains_consumed_request_metrics(self):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, read_fd)
        self.addCleanup(os.close, write_fd)
        client = LeanRepl(Path("."), timeout_seconds=5.0)
        client._master_fd = write_fd
        client._process = Mock(pid=10)
        client._read_response = Mock(side_effect=ReplTimeout("deadline"))
        client.close = Mock()
        with (
            patch("lean_prefix.repl._largest_descendant", return_value=42),
            patch("lean_prefix.repl._proc_cpu_seconds", side_effect=[1.0, 3.5]),
            patch("lean_prefix.repl._proc_peak_rss_kib", return_value=123_456),
            self.assertRaises(ReplTimeout) as raised,
        ):
            client.request({"cmd": "slow"})
        self.assertGreaterEqual(raised.exception.wall_seconds, 0.0)
        self.assertEqual(raised.exception.cpu_seconds, 2.5)
        self.assertEqual(raised.exception.peak_rss_kib, 123_456)
        self.assertEqual(raised.exception.stderr, "")
        client.close.assert_called_once_with()

    def test_request_returns_only_its_stderr_delta(self):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, read_fd)
        self.addCleanup(os.close, write_fd)
        stderr = tempfile.TemporaryFile(mode="w+b")
        self.addCleanup(stderr.close)
        stderr.write(b"startup noise\n")
        stderr.flush()
        client = LeanRepl(Path("."), timeout_seconds=5.0)
        client._master_fd = write_fd
        client._stderr = stderr
        client._process = Mock(pid=10)

        def respond(_deadline):
            stderr.write(b"request profile\n")
            stderr.flush()
            return {"env": 1}

        client._read_response = Mock(side_effect=respond)
        with (
            patch("lean_prefix.repl._largest_descendant", return_value=42),
            patch("lean_prefix.repl._proc_cpu_seconds", side_effect=[1.0, 1.5]),
            patch("lean_prefix.repl._proc_peak_rss_kib", return_value=123),
        ):
            result = client.request({"cmd": "example"})
        self.assertEqual(result.stderr, "request profile\n")
        self.assertEqual(result.cpu_seconds, 0.5)


if __name__ == "__main__":
    unittest.main()
