from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from lean_prefix.audit import sha256_file
from lean_prefix.corpus import iter_proposals


class CorpusTests(unittest.TestCase):
    def test_registered_identity_and_padding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = [
                {"theorem_name": "a", "proof": "p0", "correct": True},
                {"theorem_name": "a", "proof": "p1", "correct": False},
                {"theorem_name": "a", "proof": "padding", "correct": True},
            ]
            data = root / "proofs.jsonl"
            data.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
            manifest = {
                "schema_version": 1,
                "name": "fixture",
                "source_root_default": str(root),
                "samples_per_theorem": 2,
                "expected": {
                    "raw_proposals": 3,
                    "registered_proposals": 2,
                    "registered_correct": 1,
                    "theorems": 1,
                    "padding_proposals": 1,
                    "padding_by_theorem": {"a": 1},
                },
                "partitions": [
                    {"path": "proofs.jsonl", "sha256": sha256_file(data), "raw_proposals": 3}
                ],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            registered = list(iter_proposals(manifest_path))
            self.assertEqual([row.candidate_index for row in registered], [0, 1])
            self.assertEqual(len({row.proposal_id for row in registered}), 2)
            self.assertTrue(all(row.registered for row in registered))

            physical = list(iter_proposals(manifest_path, include_padding=True))
            self.assertEqual(len(physical), 3)
            self.assertFalse(physical[-1].registered)
            self.assertEqual(physical[-1].candidate_index, 2)


if __name__ == "__main__":
    unittest.main()

