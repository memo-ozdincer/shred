"""Reproducible corpus-level analyses that do not interpret Lean syntax."""

from __future__ import annotations

from collections import defaultdict
import hashlib
from pathlib import Path
from typing import Any

from lean_prefix.corpus import iter_proposals


def _proof_hash(proof: str) -> str:
    return hashlib.sha256(proof.encode("utf-8")).hexdigest()


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * probability)
    return ordered[index]


def analyze_exact(manifest_path: Path, source_root: Path | None = None) -> dict[str, Any]:
    by_theorem: dict[str, list[str]] = defaultdict(list)
    proof_bytes: list[float] = []
    telemetry_times: list[float] = []
    telemetry_rows = 0
    registered_correct = 0

    for proposal in iter_proposals(manifest_path, source_root):
        proof_hash = _proof_hash(proposal.proof)
        by_theorem[proposal.theorem_name].append(proof_hash)
        registered_correct += int(proposal.correct)
        proof_bytes.append(float(len(proposal.proof.encode("utf-8"))))
        verification_time = proposal.record.get("verification_time")
        if isinstance(verification_time, (int, float)):
            telemetry_rows += 1
            telemetry_times.append(float(verification_time))

    proposals = sum(len(proofs) for proofs in by_theorem.values())
    unique_proofs = sum(len(set(proofs)) for proofs in by_theorem.values())
    theorems_with_duplicates = sum(len(set(proofs)) < len(proofs) for proofs in by_theorem.values())
    duplicate_occurrences = proposals - unique_proofs

    return {
        "analysis": "exact-complete-proof-v1",
        "theorems": len(by_theorem),
        "proposals": proposals,
        "correct": registered_correct,
        "unique_exact_proofs_within_theorem": unique_proofs,
        "duplicate_proposal_occurrences": duplicate_occurrences,
        "duplicate_proposal_share": duplicate_occurrences / proposals,
        "whole_proof_oracle_ratio": proposals / unique_proofs,
        "theorems_with_exact_duplicates": theorems_with_duplicates,
        "theorem_duplicate_share": theorems_with_duplicates / len(by_theorem),
        "proof_bytes": {
            "median": _quantile(proof_bytes, 0.5),
            "p90": _quantile(proof_bytes, 0.9),
            "p99": _quantile(proof_bytes, 0.99),
            "max": max(proof_bytes, default=None),
        },
        "per_proposal_verifier_telemetry": {
            "rows": telemetry_rows,
            "coverage": telemetry_rows / proposals,
            "verification_seconds": {
                "median": _quantile(telemetry_times, 0.5),
                "p90": _quantile(telemetry_times, 0.9),
                "p95": _quantile(telemetry_times, 0.95),
                "p99": _quantile(telemetry_times, 0.99),
                "max": max(telemetry_times, default=None),
            },
        },
    }
