"""Digest-only export of OProver capture output to SHRED trace records."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Iterator

from .oprover_adapter import (
    OProverAdapterError,
    split_boundary_stderr,
    summarize_cpu_boundaries,
)


class OProverExportError(RuntimeError):
    """Raised when producer output cannot support an exact trace record."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _execution_scope(capture: dict[str, Any], location: str) -> str:
    """Hash the producer-owned group and fresh REPL lease identity."""
    group_id = _required_text(capture, "group_id", location)
    repl_uuid = _required_text(capture, "repl_uuid", location)
    group_index = capture.get("group_index")
    group_size = capture.get("group_size")
    if (
        isinstance(group_index, bool)
        or not isinstance(group_index, int)
        or group_index < 0
    ):
        raise OProverExportError(f"{location}: invalid group_index")
    if (
        isinstance(group_size, bool)
        or not isinstance(group_size, int)
        or group_size < 8
        or group_index >= group_size
    ):
        raise OProverExportError(f"{location}: invalid group_size")
    return _sha256_text(f"oprover-kimina-v1\0{group_id}\0{repl_uuid}")


def _required_text(row: dict[str, Any], field: str, location: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise OProverExportError(f"{location}: missing nonempty {field}")
    return value


def _verdict(row: dict[str, Any]) -> str:
    if row.get("success") is True:
        return "accepted"
    error_type = row.get("error_type")
    if error_type in {"timeout", "batch_timeout"}:
        return "timed_out"
    if error_type in {"server_error", "http_timeout", "exception"}:
        return "crashed"
    return "rejected"


def _digest(value: Any, field: str, location: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise OProverExportError(f"{location}: invalid {field}")
    return value


def normalize_saved_attempt(row: dict[str, Any], location: str) -> dict[str, Any]:
    """Convert one saved OProver attempt without loading any checkpoint."""
    proposal_id = _required_text(row, "proposal_id", location)
    formal = _required_text(row, "formal_statement", location)
    extracted = _required_text(row, "extracted_code", location)
    global_step = row.get("global_step")
    if isinstance(global_step, bool) or not isinstance(global_step, int):
        raise OProverExportError(f"{location}: invalid global_step")
    statement_digest = _sha256_text(formal)
    record = {
        "proposal_id": f"step{global_step}/{proposal_id}",
        "proposal_sha256": _sha256_text(extracted),
        "theorem_name": f"sha256:{statement_digest}",
        "theorem_statement_sha256": statement_digest,
        "verdict": _verdict(row),
    }

    capture = row.get("shred_cpu_capture")
    if not isinstance(capture, dict):
        raise OProverExportError(f"{location}: missing SHRED capture receipt")
    status = capture.get("status")
    if status == "cached_exact_duplicate":
        representative = _required_text(capture, "representative_id", location)
        record.update(
            {
                "full_verifier_cpu_seconds": 0.0,
                "eligibility": "fallback",
                "fallback_reason": "existing_exact_duplicate_cache",
                "baseline_execution": "cached_exact_duplicate",
                "cache_representative_id": f"step{global_step}/{representative}",
            }
        )
        return record
    if status != "captured":
        reason = capture.get("fallback_reason", "capture_not_exact")
        raise OProverExportError(
            f"{location}: executed attempt lacks exact process CPU ({reason})"
        )

    boundary_lines = capture.get("cpu_boundaries")
    native_tactics = capture.get("native_tactics")
    if not isinstance(boundary_lines, list) or not all(
        isinstance(line, str) for line in boundary_lines
    ):
        raise OProverExportError(f"{location}: invalid native CPU boundary list")
    if not isinstance(native_tactics, list) or not all(
        isinstance(tactic, dict) for tactic in native_tactics
    ):
        raise OProverExportError(f"{location}: invalid native tactic list")
    try:
        boundaries, unrelated = split_boundary_stderr("\n".join(boundary_lines))
        if unrelated:
            raise OProverExportError(
                f"{location}: unrelated stderr mixed into CPU boundaries"
            )
        summary = summarize_cpu_boundaries(boundaries, native_tactics)
    except OProverAdapterError as error:
        raise OProverExportError(f"{location}: {error}") from error
    full_cpu = summary["full_verifier_cpu_seconds"]
    if not isinstance(full_cpu, (int, float)) or not math.isfinite(full_cpu):
        raise OProverExportError(f"{location}: non-finite full process CPU")
    record["full_verifier_cpu_seconds"] = float(full_cpu)
    record["baseline_execution"] = "warm_complete_attempt"

    checkpoint = capture.get("checkpoint")
    if not isinstance(checkpoint, dict):
        raise OProverExportError(f"{location}: missing checkpoint receipt")
    if checkpoint.get("status") == "fallback":
        record.update(
            {
                "eligibility": "fallback",
                "fallback_reason": _required_text(
                    checkpoint, "fallback_reason", location
                ),
            }
        )
        return record
    if checkpoint.get("status") != "captured":
        raise OProverExportError(f"{location}: invalid checkpoint status")

    prefix_length = checkpoint.get("prefix_length")
    steps = summary.get("native_tactics")
    if (
        isinstance(prefix_length, bool)
        or not isinstance(prefix_length, int)
        or prefix_length < 1
        or not isinstance(steps, list)
        or prefix_length >= len(steps)
    ):
        raise OProverExportError(f"{location}: invalid checkpoint prefix length")
    prefix_cpu = steps[prefix_length - 1].get("prefix_verifier_cpu_seconds")
    if (
        not isinstance(prefix_cpu, (int, float))
        or isinstance(prefix_cpu, bool)
        or not math.isfinite(prefix_cpu)
        or prefix_cpu < 0
        or prefix_cpu > full_cpu
    ):
        raise OProverExportError(f"{location}: invalid prefix process CPU")
    record.update(
        {
            "eligibility": "exact_checkpoint",
            "execution_scope_sha256": _execution_scope(capture, location),
            "prefix_verifier_cpu_seconds": float(prefix_cpu),
            "parent_environment_sha256": _digest(
                checkpoint.get("parent_environment_sha256"),
                "parent_environment_sha256",
                location,
            ),
            "root_context_sha256": _digest(
                checkpoint.get("root_context_sha256"),
                "root_context_sha256",
                location,
            ),
            "prefix_edges_sha256": _digest(
                checkpoint.get("prefix_edges_sha256"),
                "prefix_edges_sha256",
                location,
            ),
            "checkpoint_artifact_sha256": _digest(
                checkpoint.get("checkpoint_artifact_sha256"),
                "checkpoint_artifact_sha256",
                location,
            ),
        }
    )
    return record


def _rows(path: Path) -> Iterator[tuple[str, dict[str, Any]]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                raise OProverExportError(f"{path}:{line_number}: blank record")
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise OProverExportError(
                    f"{path}:{line_number}: invalid JSON"
                ) from error
            if not isinstance(row, dict):
                raise OProverExportError(f"{path}:{line_number}: record is not an object")
            yield f"{path}:{line_number}", row


def export_saved_attempts(
    inputs: Iterable[Path], output: Path, expected_attempts: int
) -> dict[str, Any]:
    """Export immutable digest-only JSONL without overwriting producer data."""
    paths = [Path(path).resolve() for path in inputs]
    destination = Path(output).resolve()
    if not paths:
        raise OProverExportError("at least one input partition is required")
    if len(set(paths)) != len(paths):
        raise OProverExportError("input partitions must be unique")
    if expected_attempts < 1:
        raise OProverExportError("expected_attempts must be positive")
    if destination.exists():
        raise OProverExportError(f"refusing to overwrite {destination}")
    if not destination.name.endswith(".jsonl"):
        raise OProverExportError("output must end in .jsonl")
    if destination in paths:
        raise OProverExportError("output cannot be an input partition")
    for path in paths:
        if not path.is_file():
            raise OProverExportError(f"input partition does not exist: {path}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    count = exact = fallback = cached = 0
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            for path in paths:
                before = path.stat()
                for location, row in _rows(path):
                    record = normalize_saved_attempt(row, location)
                    temporary.write(
                        json.dumps(record, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    )
                    count += 1
                    exact += record["eligibility"] == "exact_checkpoint"
                    fallback += record["eligibility"] == "fallback"
                    cached += record.get("baseline_execution") == "cached_exact_duplicate"
                after = path.stat()
                if (
                    before.st_dev,
                    before.st_ino,
                    before.st_size,
                    before.st_mtime_ns,
                ) != (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                ):
                    raise OProverExportError(
                        f"producer partition changed during export: {path}"
                    )
            temporary.flush()
            os.fsync(temporary.fileno())
        if count != expected_attempts:
            raise OProverExportError(
                f"producer-declared expected_attempts={expected_attempts}, found {count}"
            )
        try:
            os.link(temporary_name, destination)
        except FileExistsError as error:
            raise OProverExportError(f"refusing to overwrite {destination}") from error
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
    return {
        "output": str(destination),
        "records": count,
        "exact_checkpoint": exact,
        "fallback": fallback,
        "cached_exact_duplicate": cached,
    }
