"""Create immutable SHRED manifests for external rollout corpora."""

from __future__ import annotations

from collections import defaultdict
import gzip
import json
import os
from pathlib import Path
from typing import Any, Iterable

from lean_prefix.audit import sha256_content, sha256_file


class ManifestError(RuntimeError):
    """Raised when rollout data cannot be registered without ambiguity."""


def _records(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, mode="rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ManifestError(f"invalid JSON at {path}:{line_number}: {error}") from error
            missing = {"theorem_name", "proof", "correct"} - record.keys()
            if missing:
                raise ManifestError(
                    f"missing {', '.join(sorted(missing))} at {path}:{line_number}"
                )
            yield line_number, record


def create_manifest(
    inputs: list[Path],
    output: Path,
    *,
    samples_per_theorem: int,
    name: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Register JSONL inputs without copying or rewriting their contents."""
    if not inputs:
        raise ManifestError("at least one input is required")
    if samples_per_theorem < 1:
        raise ManifestError("samples per theorem must be positive")
    output = output.resolve()
    if output.exists() and not force:
        raise ManifestError(f"refusing to overwrite manifest {output}")
    resolved = [path.resolve() for path in inputs]
    missing_paths = [str(path) for path in resolved if not path.is_file()]
    if missing_paths:
        raise ManifestError(f"missing input: {', '.join(missing_paths)}")

    source_root = Path(os.path.commonpath([str(path.parent) for path in resolved]))
    theorem_counts: dict[str, int] = defaultdict(int)
    registered_correct = 0
    raw_proposals = 0
    partitions: list[dict[str, Any]] = []
    for path in resolved:
        rows = 0
        for _, record in _records(path):
            rows += 1
            raw_proposals += 1
            theorem = str(record["theorem_name"])
            theorem_counts[theorem] += 1
            if theorem_counts[theorem] <= samples_per_theorem:
                registered_correct += int(bool(record["correct"]))
        partitions.append({
            "path": os.path.relpath(path, source_root),
            "sha256": sha256_file(path),
            "content_sha256": sha256_content(path),
            "raw_proposals": rows,
        })

    incomplete = {
        theorem: count
        for theorem, count in theorem_counts.items()
        if count < samples_per_theorem
    }
    if incomplete:
        preview = dict(list(sorted(incomplete.items()))[:5])
        raise ManifestError(
            f"theorems below the declared proposal budget: {preview}"
        )
    padding_by_theorem = {
        theorem: count - samples_per_theorem
        for theorem, count in theorem_counts.items()
        if count > samples_per_theorem
    }
    registered_proposals = len(theorem_counts) * samples_per_theorem
    manifest = {
        "schema_version": 1,
        "name": name or output.stem,
        "source_root_default": os.path.relpath(source_root, output.parent),
        "samples_per_theorem": samples_per_theorem,
        "expected": {
            "raw_proposals": raw_proposals,
            "registered_proposals": registered_proposals,
            "registered_correct": registered_correct,
            "theorems": len(theorem_counts),
            "padding_proposals": raw_proposals - registered_proposals,
            "padding_by_theorem": dict(sorted(padding_by_theorem.items())),
        },
        "partitions": partitions,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
