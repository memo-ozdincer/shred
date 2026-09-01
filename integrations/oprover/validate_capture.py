#!/usr/bin/env python3
"""Validate the pinned SHRED Lean/REPL capture protocol on one tiny fixture.

This is a correctness check.  Its CPU values are deliberately not retained or
reported as performance evidence.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from shred.oprover_adapter import split_boundary_stderr, summarize_cpu_boundaries


EXPECTED_TACTICS = [
    "Lean.Parser.Tactic.constructor",
    "Lean.Parser.Tactic.exact",
    "Lean.Parser.Tactic.exact",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lake", type=Path, required=True)
    parser.add_argument("--repl", type=Path, required=True)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path(__file__).parent / "fixtures" / "capture-request.json",
    )
    return parser.parse_args()


def _run(
    *, lake: Path, repl: Path, project_dir: Path, request: dict[str, Any], enabled: bool
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if enabled:
        environment["LEAN_SHRED_CPU_BOUNDARIES"] = "1"
    else:
        environment.pop("LEAN_SHRED_CPU_BOUNDARIES", None)
    return subprocess.run(
        [str(lake), "env", str(repl)],
        cwd=project_dir,
        env=environment,
        input=json.dumps(request) + "\n\n",
        text=True,
        capture_output=True,
        check=False,
    )


def _response(process: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    if process.returncode != 0:
        raise RuntimeError(f"REPL exited with status {process.returncode}")
    value = json.loads(process.stdout)
    if not isinstance(value, dict):
        raise RuntimeError("REPL response is not one attributable JSON object")
    return value


def main() -> int:
    args = _parse_args()
    request = json.loads(args.fixture.read_text(encoding="utf-8"))

    capture_process = _run(
        lake=args.lake.resolve(),
        repl=args.repl.resolve(),
        project_dir=args.project_dir.resolve(),
        request=request,
        enabled=True,
    )
    capture_response = _response(capture_process)
    if any(
        "SHRED_CPU_BOUNDARY" in str(message)
        for message in capture_response.get("messages", [])
    ):
        raise RuntimeError("CPU records leaked into Lean diagnostic messages")
    tactics = capture_response.get("tactics")
    if not isinstance(tactics, list):
        raise RuntimeError("REPL did not return native tactics")
    if [tactic.get("syntaxKind") for tactic in tactics] != EXPECTED_TACTICS:
        raise RuntimeError("fixture returned unexpected native tactic sequence")
    records, remainder = split_boundary_stderr(capture_process.stderr)
    if remainder:
        raise RuntimeError(f"unexpected non-SHRED stderr: {remainder}")
    report = summarize_cpu_boundaries(records, tactics)

    control_process = _run(
        lake=args.lake.resolve(),
        repl=args.repl.resolve(),
        project_dir=args.project_dir.resolve(),
        request=request,
        enabled=False,
    )
    control_response = _response(control_process)
    control_records, control_remainder = split_boundary_stderr(control_process.stderr)
    if control_records or control_remainder:
        raise RuntimeError("disabled control emitted capture stderr")
    if control_response.get("tactics") != tactics:
        raise RuntimeError("capture changed native tactic output")

    print(
        json.dumps(
            {
                "status": "validated",
                "fixture_tactics": len(tactics),
                "boundary_records": report["boundary_records"],
                "parsing_boundaries": report["parsing_boundaries"],
                "elaboration_boundaries": report["elaboration_boundaries"],
                "exact_tactic_matches": len(report["native_tactics"]),
                "disabled_control_agrees": True,
                "performance_claim": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"capture validation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
