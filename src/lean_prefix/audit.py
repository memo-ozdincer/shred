"""Immutable JSONL corpus auditing.

This module intentionally knows nothing about Lean tactic parsing. Its only job
is to prove that an analysis is reading the registered source corpus.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


class AuditError(RuntimeError):
    """Raised when source data disagrees with its immutable manifest."""


@dataclass(frozen=True)
class PartitionAudit:
    path: str
    sha256: str
    content_sha256: str
    raw_proposals: int
    source_path: str | None = None


@dataclass(frozen=True)
class AuditReport:
    manifest: str
    source_root: str
    partitions: tuple[PartitionAudit, ...]
    raw_proposals: int
    raw_correct: int
    registered_proposals: int
    registered_correct: int
    theorems: int
    padding_proposals: int
    padding_by_theorem: dict[str, int]
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _open_binary_content(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rb")
    return path.open("rb")


def sha256_content(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Hash logical content, transparently decompressing reviewed gzip shards."""
    digest = hashlib.sha256()
    with _open_binary_content(path) as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("schema_version") != 1:
        raise AuditError(f"unsupported manifest schema: {manifest.get('schema_version')!r}")
    return manifest


def _records(path: Path) -> Iterable[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, mode="rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise AuditError(f"invalid JSON at {path}:{line_number}: {error}") from error
            if "theorem_name" not in record or "correct" not in record:
                raise AuditError(f"missing required fields at {path}:{line_number}")
            yield record


def audit_manifest(manifest_path: Path, source_root: Path | None = None) -> AuditReport:
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    if source_root is not None:
        root = source_root.resolve()
    else:
        declared_root = Path(manifest["source_root_default"])
        root = (
            declared_root
            if declared_root.is_absolute()
            else manifest_path.parent / declared_root
        ).resolve()
    samples = int(manifest["samples_per_theorem"])

    observed_by_theorem: dict[str, int] = defaultdict(int)
    padding_by_theorem: dict[str, int] = defaultdict(int)
    partitions: list[PartitionAudit] = []
    raw_proposals = raw_correct = registered_proposals = registered_correct = 0

    for declared in manifest["partitions"]:
        relative_path = declared["path"]
        path = root / relative_path
        if not path.is_file():
            raise AuditError(f"missing partition: {path}")
        observed_sha = sha256_file(path)
        if observed_sha != declared["sha256"]:
            raise AuditError(
                f"checksum mismatch for {path}: {observed_sha} != {declared['sha256']}"
            )
        observed_content_sha = sha256_content(path)
        expected_content_sha = declared.get("content_sha256", declared["sha256"])
        if observed_content_sha != expected_content_sha:
            raise AuditError(
                f"content checksum mismatch for {path}: "
                f"{observed_content_sha} != {expected_content_sha}"
            )

        partition_rows = 0
        for record in _records(path):
            partition_rows += 1
            raw_proposals += 1
            raw_correct += int(bool(record["correct"]))
            theorem = str(record["theorem_name"])
            observed_by_theorem[theorem] += 1
            if observed_by_theorem[theorem] <= samples:
                registered_proposals += 1
                registered_correct += int(bool(record["correct"]))
            else:
                padding_by_theorem[theorem] += 1

        if partition_rows != int(declared["raw_proposals"]):
            raise AuditError(
                f"row-count mismatch for {path}: {partition_rows} != "
                f"{declared['raw_proposals']}"
            )
        partitions.append(
            PartitionAudit(
                path=relative_path,
                sha256=observed_sha,
                content_sha256=observed_content_sha,
                raw_proposals=partition_rows,
                source_path=declared.get("source_path"),
            )
        )

    expected = manifest["expected"]
    observed = {
        "raw_proposals": raw_proposals,
        "registered_proposals": registered_proposals,
        "registered_correct": registered_correct,
        "theorems": len(observed_by_theorem),
        "padding_proposals": sum(padding_by_theorem.values()),
        "padding_by_theorem": dict(sorted(padding_by_theorem.items())),
    }
    for key, value in observed.items():
        if value != expected[key]:
            raise AuditError(f"aggregate mismatch for {key}: {value!r} != {expected[key]!r}")

    incomplete = {name: count for name, count in observed_by_theorem.items() if count < samples}
    if incomplete:
        preview = dict(list(sorted(incomplete.items()))[:5])
        raise AuditError(f"theorems below registered proposal budget: {preview}")

    return AuditReport(
        manifest=str(manifest_path),
        source_root=str(root),
        partitions=tuple(partitions),
        raw_proposals=raw_proposals,
        raw_correct=raw_correct,
        registered_proposals=registered_proposals,
        registered_correct=registered_correct,
        theorems=len(observed_by_theorem),
        padding_proposals=sum(padding_by_theorem.values()),
        padding_by_theorem=dict(sorted(padding_by_theorem.items())),
        status="valid",
    )
