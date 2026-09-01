"""Fail-closed parser for the pinned OProver/Lean CPU-boundary sidecar.

The corresponding source patches emit absolute process CPU counters from
Lean's existing native profiling scopes.  This module never executes Lean and
never infers a tactic boundary from proof text.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


BOUNDARY_PREFIX = "SHRED_CPU_BOUNDARY_V1\t"
TACTIC_CATEGORY = re.compile(r"^shred tactic execution@([0-9]+):([0-9]+)$")


class OProverAdapterError(RuntimeError):
    """Raised when native CPU-boundary telemetry is incomplete or ambiguous."""


@dataclass(frozen=True)
class CpuBoundary:
    sequence: int
    depth: int
    start_ns: int
    stop_ns: int
    category: str
    declaration: str

    @property
    def cpu_seconds(self) -> float:
        return (self.stop_ns - self.start_ns) / 1_000_000_000


def split_boundary_stderr(stderr: str) -> tuple[list[CpuBoundary], str]:
    """Extract SHRED records while preserving every unrelated stderr line."""
    records: list[CpuBoundary] = []
    remainder: list[str] = []
    sequences: set[int] = set()
    for line_number, line in enumerate(stderr.splitlines(), start=1):
        if not line.startswith(BOUNDARY_PREFIX):
            remainder.append(line)
            continue
        fields = line.split("\t")
        if len(fields) != 7 or fields[0] != "SHRED_CPU_BOUNDARY_V1":
            raise OProverAdapterError(
                f"malformed CPU boundary at stderr line {line_number}"
            )
        try:
            sequence, depth, start_ns, stop_ns = map(int, fields[1:5])
        except ValueError as error:
            raise OProverAdapterError(
                f"non-integer CPU boundary at stderr line {line_number}"
            ) from error
        if min(sequence, depth, start_ns, stop_ns) < 0 or stop_ns < start_ns:
            raise OProverAdapterError(
                f"invalid CPU boundary counters at stderr line {line_number}"
            )
        if sequence in sequences:
            raise OProverAdapterError(f"duplicate CPU boundary sequence {sequence}")
        sequences.add(sequence)
        category, declaration = fields[5], fields[6]
        if not category or "\t" in category or "\t" in declaration:
            raise OProverAdapterError(
                f"invalid CPU boundary label at stderr line {line_number}"
            )
        records.append(
            CpuBoundary(
                sequence=sequence,
                depth=depth,
                start_ns=start_ns,
                stop_ns=stop_ns,
                category=category,
                declaration=declaration,
            )
        )
    records.sort(key=lambda record: record.sequence)
    return records, "\n".join(remainder)


def _native_range(unit: dict[str, Any], index: int) -> tuple[int, int]:
    start = unit.get("start_byte", unit.get("startByte"))
    stop = unit.get("end_byte", unit.get("endByte"))
    if start is None or stop is None:
        raise OProverAdapterError(
            f"native tactic {index} lacks exact byte range"
        )
    if (
        isinstance(start, bool)
        or isinstance(stop, bool)
        or not isinstance(start, int)
        or not isinstance(stop, int)
        or start < 0
        or stop <= start
    ):
        raise OProverAdapterError(f"native tactic {index} has invalid byte range")
    return start, stop


def _native_kind(unit: dict[str, Any], index: int) -> str:
    value = unit.get("syntax_kind", unit.get("syntaxKind"))
    if not isinstance(value, str) or not value:
        raise OProverAdapterError(
            f"native tactic {index} lacks exact syntax kind"
        )
    return value


def summarize_cpu_boundaries(
    records: Iterable[CpuBoundary], native_tactics: list[dict[str, Any]]
) -> dict[str, Any]:
    """Join exact native ranges to process-CPU scopes without text heuristics.

    The full cost begins at the command parser boundary and ends after command
    elaboration.  A tactic prefix ends at the matching native tactic's runtime
    boundary.  Missing, duplicate, nested-conflicting, or out-of-order ranges
    fail closed.
    """
    rows = list(records)
    parsing = [row for row in rows if row.category == "parsing"]
    elaboration = [row for row in rows if row.category == "elaboration"]
    if not parsing or not elaboration:
        raise OProverAdapterError(
            "expected at least one parsing and one elaboration CPU boundary"
        )
    envelope = sorted(parsing + elaboration, key=lambda row: row.sequence)
    if envelope[0].category != "parsing" or envelope[-1].category != "elaboration":
        raise OProverAdapterError("command CPU boundaries are out of order")
    command_start = envelope[0].start_ns
    command_stop = envelope[-1].stop_ns
    if command_stop < command_start:
        raise OProverAdapterError("command CPU counters are out of order")
    for boundary in envelope:
        if not command_start <= boundary.start_ns <= boundary.stop_ns <= command_stop:
            raise OProverAdapterError("command CPU boundary lies outside request envelope")

    by_range: dict[tuple[int, int], list[CpuBoundary]] = {}
    for row in rows:
        match = TACTIC_CATEGORY.fullmatch(row.category)
        if match is None:
            continue
        key = (int(match.group(1)), int(match.group(2)))
        by_range.setdefault(key, []).append(row)

    steps = []
    prior_stop = command_start
    for index, unit in enumerate(native_tactics):
        byte_range = _native_range(unit, index)
        syntax_kind = _native_kind(unit, index)
        candidates = by_range.get(byte_range, [])
        if len(candidates) != 1:
            raise OProverAdapterError(
                f"native tactic {index} has {len(candidates)} CPU boundary matches"
            )
        boundary = candidates[0]
        if boundary.declaration != syntax_kind:
            raise OProverAdapterError(
                f"native tactic {index} syntax kind conflicts with CPU boundary"
            )
        if not command_start <= boundary.start_ns <= boundary.stop_ns <= command_stop:
            raise OProverAdapterError(
                f"native tactic {index} lies outside the command boundary"
            )
        if boundary.stop_ns < prior_stop:
            raise OProverAdapterError(
                f"native tactic {index} CPU boundary is not ordered"
            )
        prior_stop = boundary.stop_ns
        steps.append(
            {
                "index": index,
                "start_byte": byte_range[0],
                "end_byte": byte_range[1],
                "syntax_kind": syntax_kind,
                "boundary_sequence": boundary.sequence,
                "boundary_depth": boundary.depth,
                "prefix_verifier_cpu_seconds": (
                    boundary.stop_ns - command_start
                )
                / 1_000_000_000,
            }
        )

    return {
        "clock": "lean_process_plus_terminated_children_cpu",
        "full_verifier_cpu_seconds": (command_stop - command_start)
        / 1_000_000_000,
        "parsing_boundaries": len(parsing),
        "elaboration_boundaries": len(elaboration),
        "native_tactics": steps,
        "boundary_records": len(rows),
    }
