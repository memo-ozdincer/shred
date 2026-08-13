import gzip
import json
from pathlib import Path
import tempfile
import unittest

from lean_prefix.corpus import iter_proposals
from lean_prefix.review import ReviewSelectionError, iter_joined_records
from shred import create_manifest


class BoundedJoinTests(unittest.TestCase):
    def test_bounded_native_artifact_joins_only_requested_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus = root / "rollouts.jsonl"
            corpus.write_text(
                "".join(
                    json.dumps(row) + "\n"
                    for row in (
                        {"theorem_name": "t", "proof": "by rfl", "correct": True},
                        {"theorem_name": "t", "proof": "by simp", "correct": False},
                    )
                ),
                encoding="utf-8",
            )
            manifest = root / "manifest.json"
            create_manifest([corpus], manifest, samples_per_theorem=2)
            first = next(iter_proposals(manifest))
            artifact = root / "native.jsonl.gz"
            with gzip.open(artifact, "wt", encoding="utf-8") as stream:
                stream.write(json.dumps({"proposal_id": first.proposal_id}) + "\n")

            joined = list(iter_joined_records(manifest, artifact, None, limit=1))
            self.assertEqual(len(joined), 1)
            with self.assertRaises(ReviewSelectionError):
                list(iter_joined_records(manifest, artifact, None))


if __name__ == "__main__":
    unittest.main()
