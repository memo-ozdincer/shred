"""Summarize the bounded D-021 closing-certificate feasibility probe."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from lean_prefix.profile import _git_state


class CertificateProbeError(RuntimeError):
    """Raised when the registered certificate profile is incomplete or ambiguous."""


_PROFILE_LINE = re.compile(
    r"^(?P<label>.+?) took (?P<value>[0-9.eE+-]+)(?P<unit>ns|us|µs|ms|s)$"
)
_TOTAL_LINE = re.compile(
    r"^wall_seconds=(?P<wall>[0-9.eE+-]+) "
    r"user_seconds=(?P<user>[0-9.eE+-]+) "
    r"system_seconds=(?P<system>[0-9.eE+-]+)$"
)
_SCALES = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1.0}
_CAPTURE = "tactic execution of LeanPrefix.CertificateProbe.captureClosing"
_APPLY = "tactic execution of LeanPrefix.CertificateProbe.applyClosing"
_REGISTERED = (
    {
        "name": "81687-nlinarith",
        "theorem_name": "lean_workbook_plus_81687",
        "source_candidate_index": 0,
        "target_candidate_index": 15,
        "generator_label": "tactic execution of nlinarith",
    },
    {
        "name": "24316-positivity",
        "theorem_name": "lean_workbook_plus_24316",
        "source_candidate_index": 10,
        "target_candidate_index": 2,
        "generator_label": "tactic execution of Mathlib.Tactic.Positivity.positivity",
    },
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_certificate_probe(
    profiler_log_path: Path, *, project_root: Path | None = None
) -> dict[str, Any]:
    entries: list[tuple[str, float]] = []
    total: dict[str, float] | None = None
    for line in profiler_log_path.read_text(encoding="utf-8").splitlines():
        if match := _PROFILE_LINE.fullmatch(line.strip()):
            entries.append((
                match.group("label"),
                float(match.group("value")) * _SCALES[match.group("unit")],
            ))
        elif match := _TOTAL_LINE.fullmatch(line.strip()):
            total = {
                "wall_seconds": float(match.group("wall")),
                "user_seconds": float(match.group("user")),
                "system_seconds": float(match.group("system")),
            }
    captures = [index for index, (label, _) in enumerate(entries) if label == _CAPTURE]
    applies = [index for index, (label, _) in enumerate(entries) if label == _APPLY]
    if len(captures) != len(_REGISTERED) or len(applies) != len(_REGISTERED):
        raise CertificateProbeError(
            f"expected two capture/apply pairs, found {len(captures)}/{len(applies)}"
        )
    results: list[dict[str, Any]] = []
    previous_apply = -1
    for specification, capture_index, apply_index in zip(
        _REGISTERED, captures, applies, strict=True
    ):
        if not previous_apply < capture_index < apply_index:
            raise CertificateProbeError("capture/apply events are not strictly ordered")
        generator = [
            seconds
            for label, seconds in entries[previous_apply + 1 : capture_index]
            if label == specification["generator_label"]
        ]
        if not generator:
            raise CertificateProbeError(
                f"missing generator profile for {specification['name']}"
            )
        source_typechecks = [
            seconds
            for label, seconds in entries[capture_index + 1 : apply_index]
            if label == "type checking"
        ]
        next_capture = captures[len(results) + 1] if len(results) + 1 < len(captures) else len(entries)
        target_typechecks = [
            seconds
            for label, seconds in entries[apply_index + 1 : next_capture]
            if label == "type checking"
        ]
        if not source_typechecks or not target_typechecks:
            raise CertificateProbeError(
                f"missing source or target type-check profile for {specification['name']}"
            )
        generator_seconds = generator[-1]
        capture_seconds = entries[capture_index][1]
        apply_seconds = entries[apply_index][1]
        source_typecheck_seconds = source_typechecks[0]
        target_typecheck_seconds = target_typechecks[0]
        generated_total = generator_seconds + source_typecheck_seconds
        applied_total = apply_seconds + target_typecheck_seconds
        results.append({
            **specification,
            "generator_seconds": generator_seconds,
            "capture_overhead_seconds": capture_seconds,
            "application_seconds": apply_seconds,
            "source_typecheck_seconds": source_typecheck_seconds,
            "target_typecheck_seconds": target_typecheck_seconds,
            "generator_to_application_ratio": generator_seconds / apply_seconds,
            "generated_plus_check_seconds": generated_total,
            "applied_plus_check_seconds": applied_total,
            "generated_to_applied_plus_check_ratio": generated_total / applied_total,
        })
        previous_apply = apply_index
    if total is None:
        raise CertificateProbeError("missing process timing footer")
    return {
        "analysis": "closing-certificate-feasibility-d024-v1",
        "status": "diagnostic-feasibility",
        "warning": (
            "Two hand-selected convergent pairs establish semantic and per-hit cost "
            "feasibility; they do not estimate corpus-wide hit rate or speedup. "
            "A separately preserved rfl case fails closed at Lean's unchanged "
            "maximum recursion depth and is not included as a hit."
        ),
        "mechanism": (
            "abstract a closing tactic's assigned proof over user-visible locals, "
            "instantiate it in an exactly matched target context, require definitional "
            "type equality, and let ordinary Lean check the target declaration"
        ),
        "benchmarks": results,
        "process_timing": total,
        "inputs": {
            "profiler_log": str(profiler_log_path),
            "profiler_log_sha256": _sha256(profiler_log_path),
        },
        "revisions": {
            "project_git": _git_state((project_root or Path.cwd()).resolve()),
        },
    }
