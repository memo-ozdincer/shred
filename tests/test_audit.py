from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from lean_prefix.audit import AuditError, audit_manifest, sha256_file


class AuditTests(unittest.TestCase):
    def _fixture(self, directory: Path) -> Path:
        records = [
            {"theorem_name": "a", "proof": "p1", "correct": True},
            {"theorem_name": "a", "proof": "p2", "correct": False},
            {"theorem_name": "b", "proof": "q1", "correct": True},
            {"theorem_name": "b", "proof": "q2", "correct": False},
            {"theorem_name": "a", "proof": "padding", "correct": True},
        ]
        data = directory / "proofs.jsonl"
        data.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
        manifest = {
            "schema_version": 1,
            "source_root_default": str(directory),
            "samples_per_theorem": 2,
            "expected": {
                "raw_proposals": 5,
                "registered_proposals": 4,
                "registered_correct": 2,
                "theorems": 2,
                "padding_proposals": 1,
                "padding_by_theorem": {"a": 1},
            },
            "partitions": [
                {"path": "proofs.jsonl", "sha256": sha256_file(data), "raw_proposals": 5}
            ],
        }
        path = directory / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def test_registered_selection_and_padding_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self._fixture(Path(temporary))
            report = audit_manifest(manifest)
            self.assertEqual(report.raw_proposals, 5)
            self.assertEqual(report.raw_correct, 3)
            self.assertEqual(report.registered_proposals, 4)
            self.assertEqual(report.registered_correct, 2)
            self.assertEqual(report.padding_by_theorem, {"a": 1})
            self.assertEqual(report.status, "valid")

    def test_checksum_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = self._fixture(directory)
            with (directory / "proofs.jsonl").open("a", encoding="utf-8") as stream:
                stream.write("{}\n")
            with self.assertRaisesRegex(AuditError, "checksum mismatch"):
                audit_manifest(manifest)


if __name__ == "__main__":
    unittest.main()

