from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from lean_prefix.analysis import analyze_exact
from lean_prefix.audit import sha256_file


class ExactAnalysisTests(unittest.TestCase):
    def test_duplicates_are_scoped_to_theorem(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [
                {"theorem_name": "a", "proof": "same", "correct": True},
                {"theorem_name": "a", "proof": "same", "correct": False},
                {"theorem_name": "b", "proof": "same", "correct": True},
                {"theorem_name": "b", "proof": "other", "correct": False},
            ]
            data = root / "proofs.jsonl"
            data.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            manifest = {
                "schema_version": 1,
                "name": "fixture",
                "source_root_default": str(root),
                "samples_per_theorem": 2,
                "expected": {
                    "raw_proposals": 4,
                    "registered_proposals": 4,
                    "registered_correct": 2,
                    "theorems": 2,
                    "padding_proposals": 0,
                    "padding_by_theorem": {},
                },
                "partitions": [
                    {"path": "proofs.jsonl", "sha256": sha256_file(data), "raw_proposals": 4}
                ],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            report = analyze_exact(manifest_path)
            self.assertEqual(report["unique_exact_proofs_within_theorem"], 3)
            self.assertEqual(report["duplicate_proposal_occurrences"], 1)
            self.assertEqual(report["theorems_with_exact_duplicates"], 1)


if __name__ == "__main__":
    unittest.main()
