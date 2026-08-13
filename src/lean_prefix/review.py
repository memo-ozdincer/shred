"""Deterministic sample selection for human review of native parsing results."""

from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
from itertools import islice, zip_longest
from pathlib import Path
from typing import Any, Iterator

from lean_prefix.corpus import Proposal, iter_proposals
from lean_prefix.native import fallback_class


class ReviewSelectionError(RuntimeError):
    """Raised when an extraction artifact cannot be joined to its corpus."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_records(path: Path) -> Iterator[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else Path.open
    if path.suffix == ".gz":
        stream = opener(path, mode="rt", encoding="utf-8")
    else:
        stream = opener(path, mode="r", encoding="utf-8")
    with stream:
        for line in stream:
            yield json.loads(line)


def iter_joined_records(
    manifest_path: Path,
    artifact_path: Path,
    source_root: Path | None,
    *,
    limit: int | None = None,
) -> Iterator[tuple[Proposal, dict[str, Any]]]:
    if limit is not None and limit < 0:
        raise ReviewSelectionError("join limit must be non-negative")
    corpus = iter_proposals(manifest_path, source_root)
    artifact = _artifact_records(artifact_path)
    if limit is not None:
        corpus = islice(corpus, limit)
        artifact = islice(artifact, limit)
    sentinel = object()
    for proposal, record in zip_longest(corpus, artifact, fillvalue=sentinel):
        if proposal is sentinel or record is sentinel:
            raise ReviewSelectionError("corpus and native artifact have different lengths")
        assert isinstance(proposal, Proposal)
        assert isinstance(record, dict)
        if record.get("proposal_id") != proposal.proposal_id:
            raise ReviewSelectionError(
                f"artifact identity mismatch at {proposal.proposal_id}: "
                f"{record.get('proposal_id')!r}"
            )
        yield proposal, record


def _shared_depth(edges: list[str], counts: Counter[tuple[str, ...]]) -> int:
    depth = 0
    for stop in range(1, len(edges) + 1):
        if counts[tuple(edges[:stop])] < 2:
            break
        depth = stop
    return depth


def _offer(
    selected: dict[str, tuple[tuple[Any, ...], dict[str, Any]]],
    category: str,
    rank: tuple[Any, ...],
    example: dict[str, Any],
) -> None:
    current = selected.get(category)
    if current is None or rank > current[0]:
        selected[category] = (rank, example)


def _example(
    category: str,
    proposal: Proposal,
    record: dict[str, Any],
    *,
    shared_depth: int | None,
    theorem_oracle_ratio: float | None,
) -> dict[str, Any]:
    return {
        "category": category,
        "proposal_id": proposal.proposal_id,
        "theorem_name": proposal.theorem_name,
        "candidate_index": proposal.candidate_index,
        "correct": proposal.correct,
        "eligible": bool(record.get("eligible")),
        "error": record.get("error"),
        "shared_prefix_depth": shared_depth,
        "theorem_oracle_ratio": theorem_oracle_ratio,
        "verification_time": proposal.record.get("verification_time"),
        "proof": proposal.proof,
        "units": record.get("units", []),
        "exact_edges": record.get("exact_edges"),
    }


def select_review_sample(
    manifest_path: Path,
    artifact_path: Path,
    source_root: Path | None = None,
) -> dict[str, Any]:
    """Select fixed edge cases and high-information examples without randomness."""
    selected: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
    group: list[tuple[Proposal, dict[str, Any]]] = []
    proposals = 0
    completed_theorems: set[str] = set()

    def process_group(rows: list[tuple[Proposal, dict[str, Any]]]) -> None:
        if not rows:
            return
        prefix_counts: Counter[tuple[str, ...]] = Counter()
        proof_counts = Counter(record["proof_sha256"] for _, record in rows)
        independent_units = 0
        for _, record in rows:
            edges = record.get("exact_edges")
            if edges is None:
                continue
            independent_units += len(edges)
            for stop in range(1, len(edges) + 1):
                prefix_counts[tuple(edges[:stop])] += 1
        unique_nodes = len(prefix_counts)
        theorem_ratio = independent_units / unique_nodes if unique_nodes else 1.0

        theorem_examples: list[tuple[int, Proposal, dict[str, Any]]] = []
        for proposal, record in rows:
            edges = record.get("exact_edges")
            depth = _shared_depth(edges, prefix_counts) if edges is not None else None
            base = _example(
                "", proposal, record, shared_depth=depth, theorem_oracle_ratio=theorem_ratio
            )
            tie = tuple(-ord(char) for char in proposal.proposal_id)
            correctness = "correct" if proposal.correct else "incorrect"

            if edges is None:
                category = f"fallback_{fallback_class(record.get('error'))}"
                item = dict(base, category=category)
                _offer(selected, category, tie, item)
                continue

            length = len(edges)
            category = f"{correctness}_longest_sequence"
            _offer(selected, category, (length, tie), dict(base, category=category))

            category = f"{correctness}_deepest_shared_prefix"
            _offer(selected, category, (depth or 0, length, tie), dict(base, category=category))

            if depth == 0:
                category = f"{correctness}_no_shared_prefix"
                _offer(selected, category, tie, dict(base, category=category))

            if proof_counts[record["proof_sha256"]] >= 2:
                category = f"{correctness}_exact_duplicate"
                _offer(selected, category, (length, tie), dict(base, category=category))

            syntax_kinds = {str(unit.get("syntaxKind")) for unit in record.get("units", [])}
            if any("case" in kind or "cdot" in kind or "Bracketed" in kind for kind in syntax_kinds):
                category = f"{correctness}_structured_syntax"
                _offer(selected, category, (length, tie), dict(base, category=category))

            verification_time = proposal.record.get("verification_time")
            if isinstance(verification_time, (int, float)):
                category = f"{correctness}_slowest_with_telemetry"
                _offer(
                    selected,
                    category,
                    (float(verification_time), tie),
                    dict(base, category=category),
                )
            theorem_examples.append((depth or 0, proposal, record))

        if theorem_examples:
            _, proposal, record = max(
                theorem_examples, key=lambda item: (item[0], -item[1].candidate_index)
            )
            edges = record["exact_edges"]
            depth = _shared_depth(edges, prefix_counts)
            category = "highest_reuse_theorem_representative"
            item = _example(
                category,
                proposal,
                record,
                shared_depth=depth,
                theorem_oracle_ratio=theorem_ratio,
            )
            _offer(selected, category, (theorem_ratio, depth), item)

    previous_theorem: str | None = None
    for proposal, record in iter_joined_records(manifest_path, artifact_path, source_root):
        proposals += 1
        if previous_theorem is not None and proposal.theorem_name != previous_theorem:
            process_group(group)
            completed_theorems.add(previous_theorem)
            group = []
        if proposal.theorem_name in completed_theorems:
            raise ReviewSelectionError(
                f"non-contiguous theorem block: {proposal.theorem_name}"
            )
        group.append((proposal, record))
        previous_theorem = proposal.theorem_name
    process_group(group)

    return {
        "analysis": "deterministic-hand-review-sample-v1",
        "selection_rule": (
            "global extrema and lexicographically stable representatives across correctness, "
            "reuse, syntax, fallback, duplication, and available verifier telemetry strata"
        ),
        "manifest": str(manifest_path),
        "native_artifact": {
            "path": str(artifact_path),
            "sha256": _sha256_file(artifact_path),
        },
        "proposals_joined": proposals,
        "examples": [selected[key][1] for key in sorted(selected)],
    }
