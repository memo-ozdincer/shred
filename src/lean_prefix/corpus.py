"""Stable, read-only access to the registered C0 corpus."""

from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

from lean_prefix.audit import audit_manifest, load_manifest


def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    partition: str
    source_content_sha256: str
    source_row: int
    theorem_name: str
    candidate_index: int
    registered: bool
    record: dict[str, Any]

    @property
    def proof(self) -> str:
        return str(self.record["proof"])

    @property
    def correct(self) -> bool:
        return bool(self.record["correct"])


def _open_records(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, mode="rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def resolve_source_root(manifest_path: Path, source_root: Path | None = None) -> Path:
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    if source_root is not None:
        return source_root.resolve()
    declared = Path(manifest["source_root_default"])
    return (declared if declared.is_absolute() else manifest_path.parent / declared).resolve()


def iter_proposals(
    manifest_path: Path,
    source_root: Path | None = None,
    *,
    include_padding: bool = False,
    verify: bool = True,
) -> Iterator[Proposal]:
    """Yield proposals in physical order with deterministic corpus identities.

    The identity is tied to the immutable uncompressed source hash and row,
    rather than a mutable path or gzip representation.
    """
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    root = resolve_source_root(manifest_path, source_root)
    if verify:
        audit_manifest(manifest_path, root)

    samples = int(manifest["samples_per_theorem"])
    counts: dict[str, int] = {}
    corpus_name = str(manifest["name"])

    for partition in manifest["partitions"]:
        relative_path = str(partition["path"])
        content_sha = str(partition.get("content_sha256", partition["sha256"]))
        with _open_records(root / relative_path) as stream:
            for source_row, line in enumerate(stream):
                record = json.loads(line)
                theorem = str(record["theorem_name"])
                candidate_index = counts.get(theorem, 0)
                counts[theorem] = candidate_index + 1
                registered = candidate_index < samples
                if not registered and not include_padding:
                    continue
                proposal_id = _sha256_json(
                    {
                        "corpus": corpus_name,
                        "source_content_sha256": content_sha,
                        "source_row": source_row,
                    }
                )
                yield Proposal(
                    proposal_id=proposal_id,
                    partition=relative_path,
                    source_content_sha256=content_sha,
                    source_row=source_row,
                    theorem_name=theorem,
                    candidate_index=candidate_index,
                    registered=registered,
                    record=record,
                )

