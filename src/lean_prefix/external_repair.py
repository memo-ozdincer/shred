"""Compute-only-free structural screen for external Lean repair corpora.

This module never invokes Lean.  Exact byte prefixes are descriptive source
properties, not executable prefix matches or estimates of verifier CPU.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
from typing import Any, Iterable
import zipfile


ANALYSIS_ID = "external-repair-structural-screen-v1"
DEFAULT_OVERHEAD_FRACTION = 0.02
APRIL_REVISION = "4e3075279b4aedfb28fe435d08a8caf76272586d"
APRIL_ARCHIVE_SHA256 = (
    "6acc8b668d04ad52626b87f0ede6ad4258345a3d57ac01125a0dcf79dc3b39c8"
)
LEANPOLISH_REVISION = "e161aae6770178bf96fd6dd0eecc4715106ec7fd"
LEANPOLISH_MANIFEST_SHA256 = (
    "d4e0e1ed594a70ae0b06bd2729cdf6c415761b16208f9b8a43838ae068d5ec9c"
)
GOEDEL_PROOFS_JSONL_SHA256 = (
    "3210e41c4ed2a9d82f3f86f1ad746a9aaef6af7880c5834479fb8f07e7dd69f6"
)
_PROOF_MARKER = re.compile(rb":=\s*by\b")


class ExternalRepairError(RuntimeError):
    """Raised when an external corpus is incomplete or inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def common_prefix_bytes(left: bytes, right: bytes) -> int:
    """Return the exact common UTF-8 byte prefix length."""
    limit = min(len(left), len(right))
    index = 0
    block = 4096
    while index + block <= limit and left[index : index + block] == right[index : index + block]:
        index += block
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def lean_nontrivia_bytes(source: bytes) -> int:
    """Count bytes outside whitespace/comments with a small descriptive lexer.

    This understands nested block comments, line comments, and quoted strings,
    but it is deliberately not presented as Lean-native parsing.
    """
    index = 0
    count = 0
    block_depth = 0
    line_comment = False
    string = False
    escaped = False
    while index < len(source):
        byte = source[index]
        following = source[index + 1] if index + 1 < len(source) else None
        if line_comment:
            if byte in (10, 13):
                line_comment = False
            index += 1
            continue
        if block_depth:
            if byte == 47 and following == 45:
                block_depth += 1
                index += 2
            elif byte == 45 and following == 47:
                block_depth -= 1
                index += 2
            else:
                index += 1
            continue
        if string:
            count += 1
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                string = False
            index += 1
            continue
        if byte == 45 and following == 45:
            line_comment = True
            index += 2
        elif byte == 47 and following == 45:
            block_depth = 1
            index += 2
        elif byte == 34:
            string = True
            count += 1
            index += 1
        else:
            if not chr(byte).isspace():
                count += 1
            index += 1
    return count


def source_position_speedup(
    candidates: int,
    shared_source_fraction: float,
    overhead_fraction: float = DEFAULT_OVERHEAD_FRACTION,
) -> float:
    """Sensitivity only: pretend source position equals verifier-cost share."""
    if candidates < 1:
        raise ExternalRepairError("candidate count must be positive")
    if not 0.0 <= shared_source_fraction <= 1.0:
        raise ExternalRepairError("shared source fraction must be in [0, 1]")
    if overhead_fraction < 0.0:
        raise ExternalRepairError("overhead fraction must be nonnegative")
    independent = float(candidates)
    shared = shared_source_fraction + candidates * (1.0 - shared_source_fraction)
    return independent / (shared + overhead_fraction * independent)


def _quantiles(values: Iterable[float]) -> dict[str, float] | None:
    ordered = sorted(values)
    if not ordered:
        return None

    def at(fraction: float) -> float:
        return ordered[int(fraction * (len(ordered) - 1))]

    return {
        "minimum": ordered[0],
        "p10": at(0.10),
        "median": at(0.50),
        "p90": at(0.90),
        "p95": at(0.95),
        "maximum": ordered[-1],
    }


def _threshold_counts(values: list[float]) -> dict[str, Any]:
    return {
        "total": len(values),
        "at_least_0_50": sum(value >= 0.50 for value in values),
        "at_least_0_80": sum(value >= 0.80 for value in values),
        "at_least_0_90": sum(value >= 0.90 for value in values),
        "quantiles": _quantiles(values),
    }


def _candidate_count_summary(values: list[int]) -> dict[str, Any]:
    counts = Counter(values)
    return {
        "groups": len(values),
        "mean": sum(values) / len(values) if values else 0.0,
        "quantiles": _quantiles(float(value) for value in values),
        "groups_at_least_3": sum(value >= 3 for value in values),
        "groups_at_least_8": sum(value >= 8 for value in values),
        "groups_at_least_16": sum(value >= 16 for value in values),
        "groups_at_least_32": sum(value >= 32 for value in values),
        "histogram_1_to_32_plus": {
            str(value): counts[value] for value in range(1, 32) if counts[value]
        } | {"32_plus": sum(count for value, count in counts.items() if value >= 32)},
    }


def _proof_body_fraction(proof: bytes, prefix_bytes: int, comparison_bytes: int) -> float | None:
    markers = list(_PROOF_MARKER.finditer(proof))
    if not markers:
        return None
    start = markers[-1].end()
    denominator = max(comparison_bytes - start, 1)
    return max(0, prefix_bytes - start) / denominator


def analyze_april(archive_path: Path) -> dict[str, Any]:
    if sha256_file(archive_path) != APRIL_ARCHIVE_SHA256:
        raise ExternalRepairError("APRIL archive checksum does not match frozen revision")

    groups: dict[str, dict[str, Any]] = {}
    pair_source_fractions: list[float] = []
    pair_body_fractions: list[float] = []
    by_type: dict[str, dict[str, list[float] | int]] = defaultdict(
        lambda: {"rows": 0, "source": [], "body": []}
    )
    member_records = []
    rows = 0
    malformed = 0
    with_marker = 0
    split_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()

    with zipfile.ZipFile(archive_path) as archive:
        members = sorted(
            (info for info in archive.infolist() if info.filename.endswith(".jsonl")),
            key=lambda info: info.filename,
        )
        for info in members:
            member_rows = 0
            with archive.open(info) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8")
                for line_number, line in enumerate(text, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError as error:
                        malformed += 1
                        raise ExternalRepairError(
                            f"invalid APRIL JSON at {info.filename}:{line_number}"
                        ) from error
                    rows += 1
                    member_rows += 1
                    correct = str(row["correct_proof"]).encode()
                    incorrect = str(row["incorrect_proof"]).encode()
                    prefix = common_prefix_bytes(correct, incorrect)
                    comparison_bytes = max(len(correct), len(incorrect), 1)
                    source_fraction = prefix / comparison_bytes
                    body_fraction = _proof_body_fraction(correct, prefix, comparison_bytes)
                    pair_source_fractions.append(source_fraction)
                    if body_fraction is not None:
                        pair_body_fractions.append(body_fraction)
                        with_marker += 1
                    error_type = str(row.get("error_type") or "unknown")
                    split = str(row.get("split") or "unknown")
                    source = str(row.get("source") or "unknown")
                    typed = by_type[error_type]
                    typed["rows"] = int(typed["rows"]) + 1
                    typed["source"].append(source_fraction)  # type: ignore[union-attr]
                    if body_fraction is not None:
                        typed["body"].append(body_fraction)  # type: ignore[union-attr]
                    split_counts[split] += 1
                    source_counts[source] += 1

                    src_hash = str(row["src_hash"])
                    correct_digest = hashlib.sha256(correct).hexdigest()
                    incorrect_digest = hashlib.sha256(incorrect).hexdigest()
                    group = groups.get(src_hash)
                    if group is None:
                        group = {
                            "correct": correct,
                            "correct_digests": {correct_digest},
                            "incorrect_digests": set(),
                            "rows": 0,
                            "minimum_prefix": len(correct),
                            "maximum_candidate_bytes": len(correct),
                            "splits": set(),
                            "error_types": set(),
                        }
                        groups[src_hash] = group
                    else:
                        group["correct_digests"].add(correct_digest)
                        group["minimum_prefix"] = min(
                            group["minimum_prefix"],
                            common_prefix_bytes(group["correct"], correct),
                        )
                    group["incorrect_digests"].add(incorrect_digest)
                    group["rows"] += 1
                    group["minimum_prefix"] = min(
                        group["minimum_prefix"],
                        common_prefix_bytes(group["correct"], incorrect),
                    )
                    group["maximum_candidate_bytes"] = max(
                        group["maximum_candidate_bytes"], len(correct), len(incorrect)
                    )
                    group["splits"].add(split)
                    group["error_types"].add(error_type)
            member_records.append(
                {
                    "path": info.filename,
                    "rows": member_rows,
                    "uncompressed_bytes": info.file_size,
                    "zip_crc32": f"{info.CRC:08x}",
                }
            )

    candidate_counts = []
    group_source_fractions = []
    group_body_fractions = []
    source_sensitivity = []
    inconsistent_correct = 0
    cross_split = 0
    for group in groups.values():
        candidates = len(group["correct_digests"]) + len(group["incorrect_digests"])
        candidate_counts.append(candidates)
        maximum = max(int(group["maximum_candidate_bytes"]), 1)
        fraction = int(group["minimum_prefix"]) / maximum
        group_source_fractions.append(fraction)
        body = _proof_body_fraction(group["correct"], int(group["minimum_prefix"]), maximum)
        if body is not None:
            group_body_fractions.append(body)
        source_sensitivity.append(source_position_speedup(candidates, fraction))
        inconsistent_correct += int(len(group["correct_digests"]) != 1)
        cross_split += int(len(group["splits"]) != 1)

    return {
        "dataset": "uw-math-ai/APRIL",
        "revision": APRIL_REVISION,
        "archive": {
            "path": str(archive_path),
            "sha256": APRIL_ARCHIVE_SHA256,
            "bytes": archive_path.stat().st_size,
            "members": member_records,
        },
        "records": {
            "rows": rows,
            "malformed_rows": malformed,
            "splits": dict(sorted(split_counts.items())),
            "sources": dict(sorted(source_counts.items())),
            "proof_marker_heuristic_eligible_rows": with_marker,
        },
        "pairwise_correct_vs_incorrect": {
            "exact_source_prefix_fraction": _threshold_counts(pair_source_fractions),
            "post_by_marker_source_prefix_fraction": _threshold_counts(pair_body_fractions),
            "by_error_type": {
                name: {
                    "rows": values["rows"],
                    "exact_source_prefix_fraction": _threshold_counts(values["source"]),  # type: ignore[arg-type]
                    "post_by_marker_source_prefix_fraction": _threshold_counts(values["body"]),  # type: ignore[arg-type]
                }
                for name, values in sorted(by_type.items())
            },
        },
        "src_hash_groups": {
            "groups": len(groups),
            "groups_with_multiple_correct_proof_digests": inconsistent_correct,
            "groups_crossing_splits": cross_split,
            "candidate_count_including_one_correct_proof": _candidate_count_summary(
                candidate_counts
            ),
            "earliest_exact_source_prefix_fraction": _threshold_counts(
                group_source_fractions
            ),
            "earliest_post_by_marker_source_prefix_fraction": _threshold_counts(
                group_body_fractions
            ),
            "source_position_sensitivity_with_2pct_overhead": {
                "evidence_label": "Hypothesis",
                "quantiles": _quantiles(source_sensitivity),
                "groups_at_least_1_5x": sum(value >= 1.5 for value in source_sensitivity),
                "groups_at_least_2x": sum(value >= 2.0 for value in source_sensitivity),
            },
        },
        "replay_readiness": {
            "complete_correct_and_incorrect_source_embedded": True,
            "lean_toolchain_revision_published_per_row_or_corpus": False,
            "mathlib_revision_published_per_row_or_corpus": False,
            "historical_incorrect_error_present": True,
            "ordinary_lean_replay_required_for_any_benchmark_claim": True,
        },
    }


def _leanpolish_specs(manifest: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    specs = []
    for corpus, corpus_info in sorted(manifest["shards"].items()):
        for split in ("training_pairs", "rejected_pairs"):
            sharded = corpus_info.get("files_sharded", {}).get(split)
            if sharded:
                for item in sharded:
                    specs.append(
                        {
                            "corpus": corpus,
                            "split": split,
                            "path": root / "shards" / corpus / item["name"],
                            **item,
                        }
                    )
            else:
                item = corpus_info[split]
                specs.append(
                    {
                        "corpus": corpus,
                        "split": split,
                        "path": root / "shards" / corpus / f"{split}.jsonl.gz",
                        **item,
                    }
                )
    return specs


def _validated_gzip_rows(spec: dict[str, Any]) -> Iterable[dict[str, Any]]:
    path = Path(spec["path"])
    if not path.is_file():
        raise ExternalRepairError(f"missing LeanPolish shard: {path}")
    if path.stat().st_size != int(spec["gzip_bytes"]):
        raise ExternalRepairError(f"compressed-size mismatch: {path}")
    digest = hashlib.sha256()
    rows = 0
    with gzip.open(path, "rb") as handle:
        for raw in handle:
            digest.update(raw)
            if not raw.strip():
                continue
            rows += 1
            yield json.loads(raw)
    if rows != int(spec["rows"]):
        raise ExternalRepairError(f"row-count mismatch: {path}")
    if digest.hexdigest() != str(spec["jsonl_sha256"]):
        raise ExternalRepairError(f"logical-content checksum mismatch: {path}")


def analyze_leanpolish(root: Path, goedel_proofs_path: Path | None = None) -> dict[str, Any]:
    manifest_path = root / "MANIFEST.json"
    if sha256_file(manifest_path) != LEANPOLISH_MANIFEST_SHA256:
        raise ExternalRepairError("LeanPolish publisher manifest checksum mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    specs = _leanpolish_specs(manifest, root)
    groups: dict[str, dict[str, Any]] = {}
    corpus_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    null_attempt_id_rows = 0
    files = []

    for spec in specs:
        for row in _validated_gzip_rows(spec):
            corpus = str(row["corpus"])
            split = str(spec["split"])
            corpus_counts[corpus] += 1
            split_counts[split] += 1
            kind_counts[str(row["kind"])] += 1
            outcome_counts[str(row["outcome"])] += 1
            raw_attempt_id = row.get("attempt_id")
            if raw_attempt_id is None or str(raw_attempt_id) == "":
                null_attempt_id_rows += 1
                continue
            attempt_id = str(raw_attempt_id)
            replacement = str(row["replacement"]).encode()
            replacement_digest = hashlib.sha256(replacement).hexdigest()
            start = int(row["start_byte"])
            total = int(row["bytes_original"])
            original = str(row["original"])
            root_replacement = str(row["kind"]) == "Lean.Parser.Term.byTactic" or original.lstrip().startswith("by")
            group = groups.get(attempt_id)
            if group is None:
                group = {
                    "corpus": corpus,
                    "start": start,
                    "end": int(row["end_byte"]),
                    "total": total,
                    "file": str(row["file"]),
                    "original": original.encode(),
                    "replacement_digests": set(),
                    "replacement_prefix": replacement,
                    "training": 0,
                    "rejected": 0,
                    "root_replacement": root_replacement,
                    "inconsistent_reasons": set(),
                }
                groups[attempt_id] = group
            else:
                if group["corpus"] != corpus:
                    group["inconsistent_reasons"].add("corpus")
                if group["start"] != start:
                    group["inconsistent_reasons"].add("start_byte")
                if group["total"] != total:
                    group["inconsistent_reasons"].add("bytes_original")
                if group["end"] != int(row["end_byte"]):
                    group["inconsistent_reasons"].add("end_byte")
                if group["file"] != str(row["file"]):
                    group["inconsistent_reasons"].add("file")
                if group["original"] != original.encode():
                    group["inconsistent_reasons"].add("original")
                if group["root_replacement"] != root_replacement:
                    group["inconsistent_reasons"].add("root_classification")
            group["replacement_digests"].add(replacement_digest)
            prefix = group["replacement_prefix"]
            group["replacement_prefix"] = prefix[
                : common_prefix_bytes(prefix, replacement)
            ]
            group["training" if split == "training_pairs" else "rejected"] += 1
        path = Path(spec["path"])
        files.append(
            {
                "path": str(path),
                "compressed_bytes": path.stat().st_size,
                "compressed_sha256": sha256_file(path),
                "logical_jsonl_sha256": spec["jsonl_sha256"],
                "logical_jsonl_bytes": spec["jsonl_bytes"],
                "rows": spec["rows"],
                "corpus": spec["corpus"],
                "split": spec["split"],
            }
        )

    candidate_counts = []
    source_fractions = []
    local_source_fractions = []
    root_source_fractions = []
    source_sensitivity = []
    inconsistent = 0
    inconsistent_reasons: Counter[str] = Counter()
    missing_winner = 0
    no_sibling = 0
    for group in groups.values():
        candidates = len(group["replacement_digests"])
        candidate_counts.append(candidates)
        total = max(int(group["total"]), 1)
        known_prefix = int(group["start"]) + len(group["replacement_prefix"])
        fraction = min(known_prefix / total, 1.0)
        source_fractions.append(fraction)
        if group["root_replacement"]:
            root_source_fractions.append(fraction)
        else:
            local_source_fractions.append(fraction)
        source_sensitivity.append(source_position_speedup(candidates, fraction))
        inconsistent += int(bool(group["inconsistent_reasons"]))
        inconsistent_reasons.update(group["inconsistent_reasons"])
        missing_winner += int(group["training"] == 0)
        no_sibling += int(candidates < 2)

    def cohort_summary(selected: list[dict[str, Any]]) -> dict[str, Any]:
        counts = [len(group["replacement_digests"]) for group in selected]
        fractions = []
        sensitivities = []
        corpora: Counter[str] = Counter()
        for group in selected:
            candidates = len(group["replacement_digests"])
            total = max(int(group["total"]), 1)
            known_prefix = int(group["start"]) + len(group["replacement_prefix"])
            fraction = min(known_prefix / total, 1.0)
            fractions.append(fraction)
            sensitivities.append(source_position_speedup(candidates, fraction))
            corpora[str(group["corpus"])] += 1
        return {
            "groups": len(selected),
            "corpora": dict(sorted(corpora.items())),
            "candidate_count": _candidate_count_summary(counts),
            "known_exact_file_source_prefix_fraction": _threshold_counts(fractions),
            "source_position_sensitivity_with_2pct_overhead": {
                "evidence_label": "Hypothesis",
                "quantiles": _quantiles(sensitivities),
                "groups_at_least_1_5x": sum(value >= 1.5 for value in sensitivities),
                "groups_at_least_2x": sum(value >= 2.0 for value in sensitivities),
            },
        }

    eligible = [
        group
        for group in groups.values()
        if not group["inconsistent_reasons"]
        and group["training"] > 0
        and len(group["replacement_digests"]) >= 2
    ]
    eligible_local = [group for group in eligible if not group["root_replacement"]]

    goedel_anchor: dict[str, Any] | None = None
    if goedel_proofs_path is not None:
        if sha256_file(goedel_proofs_path) != GOEDEL_PROOFS_JSONL_SHA256:
            raise ExternalRepairError("converted Goedel proof checksum mismatch")
        proofs: dict[str, bytes] = {}
        with goedel_proofs_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ExternalRepairError(
                        f"invalid Goedel proof JSON at line {line_number}"
                    ) from error
                proofs[str(row["problem_id"])] = str(row["full_proof"]).encode()

        anchored_fractions = []
        anchored_nontrivia_fractions = []
        anchored_sensitivities = []
        anchored_nontrivia_sensitivities = []
        anchored_counts = []
        anchored_nontrivia_pairs: list[tuple[int, float]] = []
        failures: Counter[str] = Counter()
        for group in eligible_local:
            if group["corpus"] != "goedel":
                continue
            problem_id = Path(str(group["file"])).stem
            source = proofs.get(problem_id)
            if source is None:
                failures["missing_source"] += 1
                continue
            if len(source) != int(group["total"]):
                failures["source_size_mismatch"] += 1
                continue
            start = int(group["start"])
            end = int(group["end"])
            if source[start:end] != group["original"]:
                failures["original_span_mismatch"] += 1
                continue
            markers = [match for match in _PROOF_MARKER.finditer(source) if match.end() <= start]
            if not markers:
                failures["no_preceding_by_marker"] += 1
                continue
            proof_start = markers[-1].end()
            proof_bytes = max(len(source) - proof_start, 1)
            shared_bytes = start + len(group["replacement_prefix"]) - proof_start
            fraction = min(max(shared_bytes / proof_bytes, 0.0), 1.0)
            proof_nontrivia = max(lean_nontrivia_bytes(source[proof_start:]), 1)
            shared_nontrivia = lean_nontrivia_bytes(source[proof_start:start])
            shared_nontrivia += lean_nontrivia_bytes(group["replacement_prefix"])
            nontrivia_fraction = min(shared_nontrivia / proof_nontrivia, 1.0)
            candidates = len(group["replacement_digests"])
            anchored_fractions.append(fraction)
            anchored_nontrivia_fractions.append(nontrivia_fraction)
            anchored_counts.append(candidates)
            anchored_nontrivia_pairs.append((candidates, nontrivia_fraction))
            anchored_sensitivities.append(source_position_speedup(candidates, fraction))
            anchored_nontrivia_sensitivities.append(
                source_position_speedup(candidates, nontrivia_fraction)
            )
        goedel_anchor = {
            "source": {
                "dataset": "Goedel-LM/Lean-workbook-proofs",
                "revision": "b731852af8d8ab11498fda27bce9020738c01c59",
                "converted_jsonl_path": str(goedel_proofs_path),
                "converted_jsonl_sha256": sha256_file(goedel_proofs_path),
                "proofs": len(proofs),
            },
            "anchored_groups": len(anchored_fractions),
            "failures": dict(sorted(failures.items())),
            "candidate_count": _candidate_count_summary(anchored_counts),
            "known_exact_proof_body_source_prefix_fraction": _threshold_counts(
                anchored_fractions
            ),
            "comment_stripped_nonwhitespace_source_prefix_fraction": _threshold_counts(
                anchored_nontrivia_fractions
            ),
            "proof_source_position_sensitivity_with_2pct_overhead": {
                "evidence_label": "Hypothesis",
                "quantiles": _quantiles(anchored_sensitivities),
                "groups_at_least_1_5x": sum(
                    value >= 1.5 for value in anchored_sensitivities
                ),
                "groups_at_least_2x": sum(
                    value >= 2.0 for value in anchored_sensitivities
                ),
            },
            "nontrivia_source_position_sensitivity_with_2pct_overhead": {
                "evidence_label": "Hypothesis",
                "quantiles": _quantiles(anchored_nontrivia_sensitivities),
                "groups_at_least_1_5x": sum(
                    value >= 1.5 for value in anchored_nontrivia_sensitivities
                ),
                "groups_at_least_2x": sum(
                    value >= 2.0 for value in anchored_nontrivia_sensitivities
                ),
            },
            "exploratory_nontrivia_cross_counts": {
                f"candidates_at_least_{minimum_candidates}": {
                    f"prefix_at_least_{minimum_prefix:.1f}": sum(
                        candidates >= minimum_candidates and fraction >= minimum_prefix
                        for candidates, fraction in anchored_nontrivia_pairs
                    )
                    for minimum_prefix in (0.5, 0.8, 0.9)
                }
                for minimum_candidates in (2, 4, 8, 16)
            },
        }

    provenance = {
        corpus: info["provenance"] for corpus, info in sorted(manifest["shards"].items())
    }
    return {
        "dataset": "leanpolish-anon/lean-proof-compression",
        "revision": LEANPOLISH_REVISION,
        "manifest": {
            "path": str(manifest_path),
            "sha256": sha256_file(manifest_path),
            "files": files,
        },
        "records": {
            "rows": sum(corpus_counts.values()),
            "corpora": dict(sorted(corpus_counts.items())),
            "splits": dict(sorted(split_counts.items())),
            "outcomes": dict(sorted(outcome_counts.items())),
            "syntax_kinds": dict(kind_counts.most_common()),
            "rows_without_attempt_id_excluded_from_grouping": null_attempt_id_rows,
        },
        "attempt_id_groups": {
            "groups": len(groups),
            "inconsistent_shared_fields": inconsistent,
            "inconsistent_field_reasons": dict(sorted(inconsistent_reasons.items())),
            "groups_without_training_winner": missing_winner,
            "groups_without_distinct_sibling": no_sibling,
            "candidate_count": _candidate_count_summary(candidate_counts),
            "known_exact_file_source_prefix_fraction": _threshold_counts(source_fractions),
            "root_by_tactic_replacement_groups": len(root_source_fractions),
            "local_replacement_groups": len(local_source_fractions),
            "local_known_exact_file_source_prefix_fraction": _threshold_counts(
                local_source_fractions
            ),
            "root_known_exact_file_source_prefix_fraction": _threshold_counts(
                root_source_fractions
            ),
            "source_position_sensitivity_with_2pct_overhead": {
                "evidence_label": "Hypothesis",
                "quantiles": _quantiles(source_sensitivity),
                "groups_at_least_1_5x": sum(value >= 1.5 for value in source_sensitivity),
                "groups_at_least_2x": sum(value >= 2.0 for value in source_sensitivity),
            },
            "consistent_multi_candidate_cohort": cohort_summary(eligible),
            "consistent_local_multi_candidate_cohort": cohort_summary(eligible_local),
            "goedel_complete_source_anchored_local_multi_candidate_cohort": goedel_anchor,
        },
        "published_provenance": provenance,
        "replay_readiness": {
            "complete_candidate_files_embedded": False,
            "source_paths_and_revisions_published": True,
            "lean_toolchain_and_mathlib_revision_published": True,
            "accepted_winners_kernel_and_file_checked": True,
            "rejected_siblings_applied_as_complete_files": False,
            "ordinary_lean_replay_required_for_any_benchmark_claim": True,
        },
    }


def _git_state() -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, text=True, capture_output=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"], check=True, text=True, capture_output=True
    ).stdout
    return {"commit": commit, "dirty": bool(status), "status_porcelain": status.splitlines()}


def build_report(
    april_archive: Path,
    leanpolish_root: Path,
    goedel_proofs_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "analysis": ANALYSIS_ID,
        "evidence_label": "Measured",
        "claim_boundary": (
            "Read-only structural analysis. Exact UTF-8 source prefixes and source-position "
            "sensitivity are not Lean-native executable prefix matches, verifier-cost "
            "fractions, measured speedups, or benchmark results. No Lean process was run."
        ),
        "method": {
            "grouping": {
                "APRIL": "src_hash; one unique correct proof plus unique incorrect proofs",
                "LeanPolish": "attempt_id; unique candidate replacement texts",
            },
            "prefix": "exact common UTF-8 bytes from complete-source root",
            "proof_marker": "descriptive regex :=\\s*by; not a Lean parser boundary",
            "nontrivia_lexer": (
                "descriptive nested-comment/string-aware byte counter; not Lean-native syntax"
            ),
            "sensitivity_formula": (
                "n / (p + n*(1-p) + 0.02*n), with source-position fraction p "
                "counterfactually substituted for verifier-cost fraction"
            ),
            "lean_invoked": False,
        },
        "runtime": {
            "git": _git_state(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "logical_cpus": os.cpu_count(),
        },
        "datasets": {
            "april": analyze_april(april_archive),
            "leanpolish": analyze_leanpolish(leanpolish_root, goedel_proofs_path),
        },
        "gate": {
            "evidence_label": "Decision",
            "minimum_target_speedup": 1.5,
            "requires_lean_native_boundaries": True,
            "requires_baseline_cost_weighting": True,
            "requires_complete_candidate_verdicts": True,
            "decision": "promising_structural_screen_but_no_lean_compute_authorized",
            "reason": (
                "Source structure may justify a later feasibility design, but neither corpus "
                "currently supplies a conservative lower bound on reusable verifier CPU."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--april-archive",
        type=Path,
        default=Path("external-data/april-4e307527/data_by_split.zip"),
    )
    parser.add_argument(
        "--leanpolish-root",
        type=Path,
        default=Path("external-data/leanpolish-e161aae6"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--goedel-proofs",
        type=Path,
        default=Path("external-data/goedel-proofs-b731852a/proofs.jsonl"),
    )
    args = parser.parse_args()
    report = build_report(args.april_archive, args.leanpolish_root, args.goedel_proofs)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
