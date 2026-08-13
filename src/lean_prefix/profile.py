"""Conservative reached-tactic cost telemetry for the Phase 2 feasibility gate."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import time
from typing import Any, Sequence

from lean_prefix.native import deterministic_gzip_text
from lean_prefix.repl import LeanRepl, ReplError, ReplResult, ReplTimeout
from lean_prefix.review import iter_joined_records


C0_BASE_CONTEXT = """import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat
"""
C0_PROMPT = """Complete the following Lean 4 code:

```lean4
"""
IN_PROCESS_PROFILE_PREFIX = (
    "set_option profiler true\n"
    "set_option profiler.threshold 0\n"
)

UNSUPPORTED_PROFILE_SYNTAX = frozenset(
    {
        "Lean.cdot",
        "Lean.calcTactic",
        "Lean.Parser.Tactic.case",
        "Lean.Parser.Tactic.tacticSeqBracketed",
        "Lean.Parser.Tactic.«tactic_<;>_»",
        "Mathlib.Tactic.induction'",
    }
)


class ReplayProfileError(RuntimeError):
    """Raised when a replay shard cannot preserve its declared invariants."""


def lean_complete(response: dict[str, Any]) -> bool:
    if "message" in response or response.get("sorries"):
        return False
    messages = response.get("messages", [])
    if any(message.get("severity") == "error" for message in messages):
        return False
    for message in messages:
        if message.get("severity") != "warning":
            continue
        data = str(message.get("data", ""))
        if "declaration uses 'sorry'" in data or "failed" in data:
            return False
    return True


def unsupported_profile_syntax(units: Sequence[dict[str, Any]]) -> list[str]:
    return sorted({
        str(unit.get("syntaxKind"))
        for unit in units
        if unit.get("syntaxKind") in UNSUPPORTED_PROFILE_SYNTAX
    })

def theorem_root_code(statement: str) -> str:
    separator = "" if statement.endswith("\n") else "\n"
    return statement + separator + "  sorry"


def c0_verifier_declaration(statement: str, proof: str) -> str | None:
    """Mirror C0's fenced-code extraction and return the declaration body."""
    code_file = C0_PROMPT + C0_BASE_CONTEXT + statement + proof
    match = re.search(r"```lean4\n(.*?)\n```", code_file, re.DOTALL)
    if match is None:
        return None
    parsed = match.group(1)
    if not parsed.startswith(C0_BASE_CONTEXT):
        raise ReplayProfileError("C0 parser returned code outside the pinned base context")
    return parsed[len(C0_BASE_CONTEXT):]


_PROFILE_LINE = re.compile(
    r"^(?P<label>.+?) took (?P<value>[0-9.eE+-]+)(?P<unit>ns|us|µs|ms|s)$"
)


def in_process_reached_steps(
    units: Sequence[dict[str, Any]], profiler_stderr: str
) -> list[dict[str, Any]]:
    """Recover a conservative reached-prefix cost from Lean's C profiler log."""
    expected = [str(unit.get("syntaxKind")) for unit in units]
    if not expected:
        return []
    scales = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1.0}
    entries: list[dict[str, Any]] = []
    for line in profiler_stderr.splitlines():
        match = _PROFILE_LINE.fullmatch(line.strip())
        if match is None:
            continue
        entries.append({
            "label": match.group("label"),
            "seconds": float(match.group("value")) * scales[match.group("unit")],
        })
    if not entries:
        return []

    def unique_ordered_indices(wanted_labels: Sequence[str]) -> tuple[str, list[int]]:
        states: dict[int, tuple[int, tuple[int, ...] | None]] = {
            index: (1, (index,))
            for index, entry in enumerate(entries)
            if entry["label"] == wanted_labels[0]
        }
        if not states:
            return "absent", []
        for wanted in wanted_labels[1:]:
            next_states: dict[int, tuple[int, tuple[int, ...] | None]] = {}
            for index, entry in enumerate(entries):
                if entry["label"] != wanted:
                    continue
                predecessors = [
                    (count, path)
                    for prior, (count, path) in states.items()
                    if prior < index
                ]
                count = min(2, sum(item_count for item_count, _ in predecessors))
                if count == 1:
                    path = next(
                        item_path
                        for item_count, item_path in predecessors
                        if item_count == 1
                    )
                    assert path is not None
                    next_states[index] = (1, path + (index,))
                elif count > 1:
                    next_states[index] = (2, None)
            states = next_states
            if not states:
                return "absent", []
        total = min(2, sum(count for count, _ in states.values()))
        if total != 1:
            return "ambiguous", []
        path = next(path for count, path in states.values() if count == 1)
        assert path is not None
        return "unique", list(path)

    matched_indices: list[int] = []
    for prefix_length in range(len(expected), 0, -1):
        status, indices = unique_ordered_indices([
            f"tactic execution of {wanted}"
            for wanted in expected[:prefix_length]
        ])
        if status == "ambiguous":
            # Syntax-kind-only profiler records cannot prove which duplicate
            # frame is the frozen top-level unit. Fail closed instead of
            # choosing a favorable alignment.
            return []
        if status == "unique":
            matched_indices = indices
            break
    if not matched_indices:
        return []

    reached: list[dict[str, Any]] = []
    for depth, entry_index in enumerate(matched_indices):
        if depth == 0:
            # Work before the first outer tactic record includes theorem
            # elaboration, so count only the tactic's own exclusive frame.
            seconds = float(entries[entry_index]["seconds"])
        else:
            seconds = sum(
                float(entry["seconds"])
                for entry in entries[matched_indices[depth - 1] + 1 : entry_index + 1]
            )
        reached.append({"tag": expected[depth], "seconds": seconds})
    return reached


def profile_alignment_outcome(
    profiled_steps: Sequence[dict[str, Any]],
    root_state: int | None,
    root_failure: dict[str, Any] | None,
) -> str:
    """Classify an in-process alignment without inventing reached work."""
    if profiled_steps:
        return "aligned"
    if root_state is not None:
        return "fallback"
    if root_failure is not None:
        return "invalid_root"
    raise ReplayProfileError("profile alignment has neither a root state nor a root failure")


def theorem_root_outcome(
    theorem: str, response: dict[str, Any]
) -> tuple[int | None, dict[str, Any] | None]:
    """Return a root state or an explicit pre-tactic Lean rejection.

    Anything else is an infrastructure/protocol failure and remains fatal.
    """
    errors = [
        message for message in response.get("messages", [])
        if message.get("severity") == "error"
    ]
    if errors:
        return None, {
            "reason": "lean_rejected_theorem_root",
            "errors": errors,
        }
    sorries = response.get("sorries", [])
    if len(sorries) == 1 and isinstance(sorries[0].get("proofState"), int):
        return int(sorries[0]["proofState"]), None
    raise ReplayProfileError(
        f"expected one root proof state for {theorem}, received {sorries!r}"
    )


def _prefix_hash(theorem_name: str, edges: Sequence[str]) -> str:
    digest = hashlib.sha256()
    digest.update(theorem_name.encode("utf-8"))
    digest.update(b"\0")
    for edge in edges:
        payload = edge.encode("utf-8")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _result_metrics(result: ReplResult) -> dict[str, Any]:
    return {
        "wall_seconds": result.wall_seconds,
        "cpu_seconds": result.cpu_seconds,
        "peak_rss_kib": result.peak_rss_kib,
    }


def _timeout_metrics(error: ReplTimeout) -> dict[str, Any]:
    return {
        "wall_seconds": error.wall_seconds,
        "cpu_seconds": error.cpu_seconds,
        "peak_rss_kib": error.peak_rss_kib,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _capture(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.stdout.strip()


def _git_state(path: Path) -> dict[str, Any]:
    return {
        "commit": _capture(["git", "rev-parse", "HEAD"], cwd=path),
        "dirty": bool(_capture(["git", "status", "--porcelain"], cwd=path)),
    }


def profile_replay_shard(
    manifest_path: Path,
    native_artifact_path: Path,
    output_artifact_path: Path,
    *,
    lean_workspace: Path,
    source_root: Path | None = None,
    shard_count: int = 1,
    shard_index: int = 0,
    limit: int | None = None,
    restart_every: int = 128,
    timeout_seconds: float = 300.0,
    memory_limit_bytes: int | None = 24 * 1024**3,
    repl_executable: Path | None = None,
    progress_every: int = 100,
    proposal_ids: set[str] | None = None,
) -> dict[str, Any]:
    if repl_executable is not None:
        repl_executable = repl_executable.resolve()
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ReplayProfileError("shard index must be in [0, shard_count)")
    if limit is not None and limit < 0:
        raise ReplayProfileError("limit must be non-negative")
    if restart_every < 1:
        raise ReplayProfileError("restart interval must be positive")
    if timeout_seconds <= 0:
        raise ReplayProfileError("timeout must be positive")
    if memory_limit_bytes is not None and memory_limit_bytes <= 0:
        raise ReplayProfileError("memory limit must be positive")
    if progress_every < 0:
        raise ReplayProfileError("progress interval must be non-negative")

    started = time.monotonic()
    client: LeanRepl | None = None
    base_env: int | None = None
    root_theorem: str | None = None
    root_proof_state: int | None = None
    root_failure: dict[str, Any] | None = None
    since_restart = 0
    selected = full_completed = verdict_matches = full_timeouts = full_errors = 0
    eligible = replay_eligible = replay_fallback = replay_fallback_units = 0
    units_total = reached_units = unreachable_units = completed_tail_units = 0
    invalid_root_units = 0
    profile_matches = profile_disagreements = root_timeouts = root_errors = 0
    root_unavailable = 0
    profiled_units = 0
    profile_timeouts = profile_errors = profile_verdict_disagreements = 0
    attributed_wall = attributed_cpu = 0.0
    full_wall = full_cpu = root_wall = root_cpu = 0.0
    profile_wall = profile_cpu = 0.0
    previous_theorem: str | None = None
    theorem_index = -1
    requested_ids = set(proposal_ids) if proposal_ids is not None else None

    def stop_client() -> None:
        nonlocal client, base_env, root_theorem, root_proof_state, root_failure, since_restart
        if client is not None:
            client.close()
        client = None
        base_env = None
        root_theorem = None
        root_proof_state = None
        root_failure = None
        since_restart = 0

    def ensure_client() -> tuple[LeanRepl, int]:
        nonlocal client, base_env
        if client is None:
            client_options: dict[str, Any] = {
                "timeout_seconds": timeout_seconds,
                "memory_limit_bytes": memory_limit_bytes,
            }
            if repl_executable is not None:
                client_options["executable"] = repl_executable
            client = LeanRepl(lean_workspace, **client_options)
            client.start()
            initialization = client.initialize(C0_BASE_CONTEXT)
            errors = [
                message for message in initialization.response.get("messages", [])
                if message.get("severity") == "error"
            ]
            if errors or not isinstance(initialization.response.get("env"), int):
                stop_client()
                raise ReplayProfileError(f"failed to initialize pinned Lean environment: {errors}")
            base_env = int(initialization.response["env"])
        assert base_env is not None
        return client, base_env

    def ensure_root(
        active: LeanRepl, env: int, theorem: str, statement: str
    ) -> tuple[int | None, dict[str, Any] | None]:
        nonlocal root_theorem, root_proof_state, root_failure, root_wall, root_cpu
        if root_theorem == theorem:
            return root_proof_state, root_failure
        root = active.elaborate(theorem_root_code(statement), env=env)
        root_wall += root.wall_seconds
        if root.cpu_seconds is not None:
            root_cpu += root.cpu_seconds
        root_proof_state, root_failure = theorem_root_outcome(theorem, root.response)
        root_theorem = theorem
        return root_proof_state, root_failure

    try:
        with deterministic_gzip_text(output_artifact_path) as output:
            for proposal, native in iter_joined_records(
                manifest_path, native_artifact_path, source_root, limit=limit
            ):
                if proposal.theorem_name != previous_theorem:
                    theorem_index += 1
                    previous_theorem = proposal.theorem_name
                if theorem_index % shard_count != shard_index:
                    continue
                if requested_ids is not None and proposal.proposal_id not in requested_ids:
                    continue
                if limit is not None and selected >= limit:
                    break
                if since_restart >= restart_every:
                    stop_client()

                selected += 1
                if requested_ids is not None:
                    requested_ids.discard(proposal.proposal_id)
                since_restart += 1
                record: dict[str, Any] = {
                    "proposal_id": proposal.proposal_id,
                    "theorem_name": proposal.theorem_name,
                    "candidate_index": proposal.candidate_index,
                    "expected_correct": proposal.correct,
                    "native_eligible": bool(native.get("eligible")),
                    "native_error": native.get("error"),
                    "native_unit_count": len(native.get("units", [])),
                    "replay_eligible": False,
                    "replay_fallback_reason": None,
                    "full": None,
                    "profile": None,
                    "steps": [],
                }
                statement = str(proposal.record["theorem_statement"])
                declaration = c0_verifier_declaration(statement, proposal.proof)
                parse_failed = declaration is None
                code = "failed to parse" if parse_failed else declaration
                try:
                    active, env = ensure_client()
                    full = active.elaborate(code, env=env, all_tactics=False)
                    full_wall += full.wall_seconds
                    if full.cpu_seconds is not None:
                        full_cpu += full.cpu_seconds
                    verdict = lean_complete(full.response)
                    full_completed += int(verdict)
                    verdict_matches += int(verdict == proposal.correct)
                    record["full"] = {
                        **_result_metrics(full),
                        "c0_parse_failed": parse_failed,
                        "complete": verdict,
                        "verdict_match": verdict == proposal.correct,
                        "message_count": len(full.response.get("messages", [])),
                        "error_messages": [
                            message.get("data")
                            for message in full.response.get("messages", [])
                            if message.get("severity") == "error"
                        ],
                        "sorry_count": len(full.response.get("sorries", [])),
                        "system_error": full.response.get("message"),
                    }
                except ReplTimeout as error:
                    full_timeouts += 1
                    timeout_match = not proposal.correct
                    verdict_matches += int(timeout_match)
                    if error.wall_seconds is not None:
                        full_wall += error.wall_seconds
                    if error.cpu_seconds is not None:
                        full_cpu += error.cpu_seconds
                    record["full"] = {
                        **_timeout_metrics(error),
                        "c0_parse_failed": parse_failed,
                        "complete": False,
                        "verdict_match": timeout_match,
                        "timed_out": True,
                        "error": str(error),
                    }
                    stop_client()
                    edges = native.get("exact_edges")
                    units = native.get("units", [])
                    if edges is not None:
                        eligible += 1
                        units_total += len(units)
                        replay_fallback += 1
                        replay_fallback_units += len(units)
                        record["replay_fallback_reason"] = (
                            "full independent verification reached its timeout"
                        )
                        record["profile"] = {
                            "supported": False,
                            "not_attempted_reason": record["replay_fallback_reason"],
                        }
                    output.write(
                        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                    )
                    continue
                except ReplError as error:
                    full_errors += 1
                    record["full"] = {"timed_out": False, "error": str(error)}
                    stop_client()
                    edges = native.get("exact_edges")
                    units = native.get("units", [])
                    if edges is not None:
                        eligible += 1
                        units_total += len(units)
                        replay_fallback += 1
                        replay_fallback_units += len(units)
                        record["replay_fallback_reason"] = (
                            "full independent verification failed at the process or "
                            "protocol level"
                        )
                        record["profile"] = {
                            "supported": False,
                            "not_attempted_reason": record["replay_fallback_reason"],
                        }
                    output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                    continue

                edges = native.get("exact_edges")
                units = native.get("units", [])
                if edges is not None:
                    eligible += 1
                    units_total += len(units)
                    if parse_failed:
                        replay_fallback += 1
                        replay_fallback_units += len(units)
                        record["replay_fallback_reason"] = "C0 fenced-code parse failure"
                        record["profile"] = {
                            "supported": False,
                            "not_attempted_reason": record["replay_fallback_reason"],
                        }
                        output.write(
                            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                        )
                        continue
                    unsupported = unsupported_profile_syntax(units)
                    if unsupported:
                        replay_fallback += 1
                        replay_fallback_units += len(units)
                        record["replay_fallback_reason"] = (
                            "unsupported structural-control syntax: "
                            + ", ".join(unsupported)
                        )
                        record["profile"] = {
                            "supported": False,
                            "not_attempted_reason": record["replay_fallback_reason"],
                        }
                        output.write(
                            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                        )
                        continue
                    assert declaration is not None
                    try:
                        profile_full = active.elaborate(
                            IN_PROCESS_PROFILE_PREFIX + declaration,
                            env=env,
                            all_tactics=False,
                        )
                        profile_wall += profile_full.wall_seconds
                        if profile_full.cpu_seconds is not None:
                            profile_cpu += profile_full.cpu_seconds
                        profile_verdict = lean_complete(profile_full.response)
                        profile_match = profile_verdict == verdict
                        profile_verdict_disagreements += int(not profile_match)
                        record["in_process_profile"] = {
                            **_result_metrics(profile_full),
                            "complete": profile_verdict,
                            "verdict_match": profile_match,
                            "profiler_stderr_bytes": len(
                                profile_full.stderr.encode("utf-8")
                            ),
                        }
                        if not profile_match:
                            raise ReplayProfileError(
                                "profile-enabled full replay changed the Lean verdict for "
                                f"{proposal.proposal_id}"
                            )
                    except ReplTimeout as error:
                        profile_timeouts += 1
                        if error.wall_seconds is not None:
                            profile_wall += error.wall_seconds
                        if error.cpu_seconds is not None:
                            profile_cpu += error.cpu_seconds
                        replay_fallback += 1
                        replay_fallback_units += len(units)
                        record["replay_fallback_reason"] = (
                            "in-process profiling request reached its timeout"
                        )
                        record["in_process_profile"] = {
                            **_timeout_metrics(error),
                            "timed_out": True,
                            "error": str(error),
                        }
                        record["profile"] = {
                            "supported": False,
                            "not_attempted_reason": record["replay_fallback_reason"],
                        }
                        stop_client()
                        output.write(
                            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                        )
                        continue
                    except ReplError as error:
                        profile_errors += 1
                        replay_fallback += 1
                        replay_fallback_units += len(units)
                        record["replay_fallback_reason"] = (
                            "in-process profiling request failed at the process or protocol level"
                        )
                        record["in_process_profile"] = {
                            "timed_out": False,
                            "error": str(error),
                        }
                        record["profile"] = {
                            "supported": False,
                            "not_attempted_reason": record["replay_fallback_reason"],
                        }
                        stop_client()
                        output.write(
                            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                        )
                        continue
                    profiled_steps = in_process_reached_steps(
                        units,
                        profile_full.stderr,
                    )
                    current_state: int | None = 0 if profiled_steps else None
                    unavailable: dict[str, Any] | None = None
                    try:
                        if current_state is None:
                            current_state, unavailable = ensure_root(
                                active,
                                env,
                                proposal.theorem_name,
                                statement,
                            )
                    except ReplTimeout as error:
                        root_timeouts += 1
                        replay_fallback += 1
                        replay_fallback_units += len(units)
                        if error.wall_seconds is not None:
                            root_wall += error.wall_seconds
                        if error.cpu_seconds is not None:
                            root_cpu += error.cpu_seconds
                        record["replay_fallback_reason"] = (
                            "theorem-root replay probe reached its timeout"
                        )
                        record["profile"] = {
                            **_timeout_metrics(error),
                            "supported": False,
                            "timed_out": True,
                            "error": str(error),
                            "not_attempted_reason": record["replay_fallback_reason"],
                        }
                        stop_client()
                        output.write(
                            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                        )
                        continue
                    except ReplError as error:
                        root_errors += 1
                        replay_fallback += 1
                        replay_fallback_units += len(units)
                        record["replay_fallback_reason"] = (
                            "theorem-root replay probe failed at the process or protocol level"
                        )
                        record["profile"] = {
                            "supported": False,
                            "timed_out": False,
                            "error": str(error),
                            "not_attempted_reason": record["replay_fallback_reason"],
                        }
                        stop_client()
                        output.write(
                            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                        )
                        continue

                    alignment_outcome = profile_alignment_outcome(
                        profiled_steps, current_state, unavailable
                    )
                    if alignment_outcome != "aligned":
                        if alignment_outcome == "fallback":
                            replay_fallback += 1
                            replay_fallback_units += len(units)
                            record["replay_fallback_reason"] = (
                                "no unique deterministic top-level alignment in the "
                                "in-process profile"
                            )
                            record["profile"] = {
                                "supported": False,
                                "not_attempted_reason": record["replay_fallback_reason"],
                            }
                        else:
                            assert alignment_outcome == "invalid_root"
                            assert unavailable is not None
                            root_unavailable += 1
                            invalid_root_units += len(units)
                            for depth, (edge, unit) in enumerate(
                                zip(edges, units, strict=True), start=1
                            ):
                                record["steps"].append({
                                    "depth": depth,
                                    "prefix_sha256": _prefix_hash(
                                        proposal.theorem_name, edges[:depth]
                                    ),
                                    "edge_sha256": hashlib.sha256(
                                        edge.encode("utf-8")
                                    ).hexdigest(),
                                    "syntax_kind": unit["syntaxKind"],
                                    "reachability": "unreachable_invalid_root",
                                    "not_attempted_reason": (
                                        "Lean rejected the theorem declaration before tactic mode"
                                    ),
                                })
                            profiled_complete = False
                            profiled_match = profiled_complete == verdict
                            profile_matches += int(profiled_match)
                            profile_disagreements += int(not profiled_match)
                            record["replay_eligible"] = True
                            replay_eligible += 1
                            record["profile"] = {
                                "method": "in_process_profile",
                                "complete": profiled_complete,
                                "verdict_match": profiled_match,
                                "root_available": False,
                                "root_failure": unavailable,
                                "reached_units": 0,
                                "unreachable_units": len(units),
                            }
                        output.write(
                            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                        )
                        if progress_every and selected % progress_every == 0:
                            elapsed = time.monotonic() - started
                            print(
                                f"profiled {selected:,} proposals in {elapsed:.1f}s "
                                f"({selected / elapsed:.2f}/s)",
                                file=os.sys.stderr,
                            )
                        continue
                    record["replay_eligible"] = True
                    replay_eligible += 1
                    profile_request_wall = profile_full.wall_seconds
                    if profile_request_wall <= 0:
                        raise ReplayProfileError(
                            "in-process profile request has non-positive wall time"
                        )
                    attributed_profile_wall = sum(
                        float(step["seconds"]) for step in profiled_steps
                    )
                    cpu_allocation_denominator = max(
                        profile_request_wall, attributed_profile_wall
                    )
                    record["in_process_profile"]["attributed_tactic_wall_seconds"] = (
                        attributed_profile_wall
                    )
                    record["in_process_profile"]["cpu_allocation_denominator_seconds"] = (
                        cpu_allocation_denominator
                    )
                    for depth, (edge, unit) in enumerate(
                        zip(edges, units, strict=True), start=1
                    ):
                        if depth <= len(profiled_steps):
                            profile_step = profiled_steps[depth - 1]
                            step_wall = float(profile_step["seconds"])
                            step_cpu = (
                                full.cpu_seconds * step_wall / cpu_allocation_denominator
                                if full.cpu_seconds is not None
                                else None
                            )
                            reached_units += 1
                            profiled_units += 1
                            attributed_wall += step_wall
                            if step_cpu is not None:
                                attributed_cpu += step_cpu
                            record["steps"].append({
                                "depth": depth,
                                "prefix_sha256": _prefix_hash(
                                    proposal.theorem_name, edges[:depth]
                                ),
                                "edge_sha256": hashlib.sha256(
                                    edge.encode("utf-8")
                                ).hexdigest(),
                                "syntax_kind": unit["syntaxKind"],
                                "reachability": "reached",
                                "wall_seconds": step_wall,
                                "cpu_seconds": step_cpu,
                                "peak_rss_kib": profile_full.peak_rss_kib,
                                "cost_source": (
                                    "Lean C-profiler attributable wall share allocated against "
                                    "unchanged full-request CPU"
                                ),
                            })
                        else:
                            reachability = (
                                "unreachable_after_completion"
                                if verdict
                                else "unreachable_after_failure"
                            )
                            if verdict:
                                completed_tail_units += 1
                            else:
                                unreachable_units += 1
                            record["steps"].append({
                                "depth": depth,
                                "prefix_sha256": _prefix_hash(
                                    proposal.theorem_name, edges[:depth]
                                ),
                                "edge_sha256": hashlib.sha256(
                                    edge.encode("utf-8")
                                ).hexdigest(),
                                "syntax_kind": unit["syntaxKind"],
                                "reachability": reachability,
                                "not_attempted_reason": (
                                    "unchanged full proof completed before this unit"
                                    if verdict
                                    else "unchanged full proof failed before this unit"
                                ),
                            })

                    profiled_complete = profile_verdict
                    profiled_match = profile_match
                    profile_matches += int(profiled_match)
                    profile_disagreements += int(not profiled_match)
                    record["profile"] = {
                        "method": "in_process_profile",
                        "complete": profiled_complete,
                        "verdict_match": profiled_match,
                        "reached_units": sum(
                            step["reachability"] == "reached" for step in record["steps"]
                        ),
                        "unreachable_units": sum(
                            step["reachability"].startswith("unreachable_")
                            for step in record["steps"]
                        ),
                    }

                output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                if progress_every and selected % progress_every == 0:
                    elapsed = time.monotonic() - started
                    print(
                        f"profiled {selected:,} proposals in {elapsed:.1f}s "
                        f"({selected / elapsed:.2f}/s)",
                        file=os.sys.stderr,
                    )
    finally:
        stop_client()

    elapsed = time.monotonic() - started
    if requested_ids:
        missing = sorted(requested_ids)
        raise ReplayProfileError(f"requested proposal IDs were not found: {missing[:10]}")
    manifest_path = manifest_path.resolve()
    native_artifact_path = native_artifact_path.resolve()
    lean_workspace = lean_workspace.resolve()
    repl_root = lean_workspace / ".lake/packages/REPL"
    resolved_repl_executable = (
        repl_executable.resolve()
        if repl_executable is not None
        else repl_root / ".lake/build/bin/repl"
    )
    return {
        "analysis": "reached-tactic-cost-profile-v2",
        "configuration": {
            "shard_count": shard_count,
            "shard_index": shard_index,
            "limit": limit,
            "restart_every": restart_every,
            "timeout_seconds": timeout_seconds,
            "memory_limit_bytes": memory_limit_bytes,
            "repl_executable": str(resolved_repl_executable),
            "proposal_id_filter_count": len(proposal_ids) if proposal_ids is not None else None,
        },
        "hardware": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "logical_cpus_visible": os.cpu_count(),
        },
        "counts": {
            "selected_proposals": selected,
            "native_eligible": eligible,
            "replay_eligible": replay_eligible,
            "replay_fallback": replay_fallback,
            "replay_fallback_units": replay_fallback_units,
            "full_completed": full_completed,
            "verdict_matches": verdict_matches,
            # A timeout is an accounted negative Lean verdict. Only protocol
            # errors lack a verdict and must be removed from this difference.
            "verdict_disagreements": selected - verdict_matches - full_errors,
            "full_timeouts": full_timeouts,
            "full_errors": full_errors,
            "native_units": units_total,
            "reached_units": reached_units,
            "unreachable_after_failure": unreachable_units,
            "unreachable_after_completion": completed_tail_units,
            "unreachable_invalid_root": invalid_root_units,
            "profile_verdict_matches": profile_matches,
            "profile_verdict_disagreements": profile_disagreements,
            "root_timeouts": root_timeouts,
            "root_errors": root_errors,
            "root_unavailable": root_unavailable,
            "profiled_units": profiled_units,
            "profile_timeouts": profile_timeouts,
            "profile_errors": profile_errors,
            "profile_verdict_disagreements": profile_verdict_disagreements,
        },
        "timing": {
            "wall_seconds": elapsed,
            "full_request_wall_seconds": full_wall,
            "full_request_cpu_seconds": full_cpu,
            "attributed_tactic_wall_seconds": attributed_wall,
            "attributed_tactic_cpu_seconds": attributed_cpu,
            "root_setup_wall_seconds": root_wall,
            "root_setup_cpu_seconds": root_cpu,
            "in_process_profile_wall_seconds": profile_wall,
            "in_process_profile_cpu_seconds": profile_cpu,
        },
        "inputs": {
            "manifest_sha256": _sha256_file(manifest_path),
            "native_artifact_sha256": _sha256_file(native_artifact_path),
        },
        "revisions": {
            "project_git": _git_state(manifest_path.parent.parent),
            "lean_workspace_git": _git_state(lean_workspace),
            "repl_git": _git_state(repl_root),
            "repl_executable_sha256": _sha256_file(resolved_repl_executable),
            "lean_toolchain": (lean_workspace / "lean-toolchain")
            .read_text(encoding="utf-8")
            .strip(),
            "lean_version": _capture(["lake", "env", "lean", "--version"], cwd=lean_workspace),
        },
        "artifact": {
            "path": str(output_artifact_path.resolve()),
            "sha256": _sha256_file(output_artifact_path),
            "bytes": output_artifact_path.stat().st_size,
        },
    }
