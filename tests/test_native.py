import unittest

from lean_prefix.native import NativeExtractionError, exact_edges, fallback_class


class NativeExtractionTests(unittest.TestCase):
    def test_exact_edges_retain_inter_tactic_trivia(self) -> None:
        proof = "  intro x\n  -- reason\n  exact x\n```"
        units = [
            {"startByte": 2, "stopByte": 9, "text": "intro x"},
            {"startByte": 24, "stopByte": 31, "text": "exact x"},
        ]
        self.assertEqual(
            exact_edges(proof, units),
            ("  intro x", "\n  -- reason\n  exact x"),
        )

    def test_invalid_native_range_fails_closed(self) -> None:
        with self.assertRaises(NativeExtractionError):
            exact_edges("  exact x\n```", [{"startByte": 2, "stopByte": 99, "text": "exact x"}])

    def test_fallback_classes_are_explicit(self) -> None:
        self.assertEqual(
            fallback_class("top-level semicolon sequence requires independent fallback"),
            "top_level_semicolon",
        )
        self.assertEqual(fallback_class("<input>:2:0: unexpected end of input"), "unexpected_end")


if __name__ == "__main__":
    unittest.main()
