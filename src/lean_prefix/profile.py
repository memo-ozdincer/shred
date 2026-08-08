"""Reached-tactic replay and cost telemetry for the Phase 2 feasibility gate."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time
from typing import Any, Sequence

from lean_prefix.native import deterministic_gzip_text, proof_body
from lean_prefix.repl import LeanRepl, ReplError, ReplResult, ReplTimeout, heartbeat_count
from lean_prefix.review import iter_joined_records


C0_BASE_CONTEXT = """import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat
"""

UNSUPPORTED_STANDALONE_SYNTAX = frozenset({"Lean.cdot", "Lean.calcTactic"})
AUXILIARY_DECLARATION_ERROR = (
    "auxiliary declaration cannot be created when declaration name is not available"
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


def proof_step_succeeded(response: dict[str, Any]) -> bool:
    return (
        "message" not in response
        and not response.get("sorries")
        and isinstance(response.get("proofState"), int)
        and not any(
            message.get("severity") == "error"
            for message in response.get("messages", [])
        )
    )


def requires_runtime_fallback(response: dict[str, Any]) -> bool:
    return any(
        message.get("severity") == "error"
        and AUXILIARY_DECLARATION_ERROR in str(message.get("data", ""))
        for message in response.get("messages", [])
    )


def unsupported_standalone_syntax(units: Sequence[dict[str, Any]]) -> list[str]:
    return sorted({
        str(unit.get("syntaxKind"))
        for unit in units
        if unit.get("syntaxKind") in UNSUPPORTED_STANDALONE_SYNTAX
    })


def theorem_root_code(statement: str) -> str:
    separator = "" if statement.endswith("\n") else "\n"
    return statement + separator + "  sorry"


def theorem_root_outcome(
    theorem: str, response: dict[str, Any]
) -> tuple[int | None, dict[str, Any] | None]:
    """Return a root state or an explicit pre-tactic Lean rejection.

    Anything else is an infrastructure/protocol failure and remains fatal.
    """
    sorries = response.get("sorries", [])
    if len(sorries) == 1 and isinstance(sorries[0].get("proofState"), int):
        return int(sorries[0]["proofState"]), None
    errors = [
        message for message in response.get("messages", [])
        if message.get("severity") == "error"
    ]
    if errors:
        return None, {
            "reason": "lean_rejected_theorem_root",
            "errors": errors,
        }
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
    units_total = reached_units = unreachable_units = invalid_root_units = 0
    sequential_matches = sequential_disagreements = root_timeouts = root_errors = 0
    root_unavailable = 0
    replayed_units = replay_timeouts = replay_errors = 0
    heartbeat_total = 0
    replay_wall = replay_cpu = full_wall = full_cpu = root_wall = root_cpu = 0.0
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
                manifest_path, native_artifact_path, source_root
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
                    "sequential": None,
                    "steps": [],
                }
                code = str(proposal.record["theorem_statement"]) + proof_body(proposal.proof)
                try:
                    active, env = ensure_client()
                    full = active.elaborate(code, env=env)
                    full_wall += full.wall_seconds
                    if full.cpu_seconds is not None:
                        full_cpu += full.cpu_seconds
                    verdict = lean_complete(full.response)
                    full_completed += int(verdict)
                    verdict_matches += int(verdict == proposal.correct)
                    record["full"] = {
                        **_result_metrics(full),
                        "complete": verdict,
                        "verdict_match": verdict == proposal.correct,
                        "message_count": len(full.response.get("messages", [])),
                        "sorry_count": len(full.response.get("sorries", [])),
                        "system_error": full.response.get("message"),
                    }
                except ReplTimeout as error:
                    full_timeouts += 1
                    record["full"] = {"timed_out": True, "error": str(error)}
                    stop_client()
                    output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                    continue
                except ReplError as error:
                    full_errors += 1
                    record["full"] = {"timed_out": False, "error": str(error)}
                    stop_client()
                    output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                    continue

                edges = native.get("exact_edges")
                units = native.get("units", [])
                if edges is not None:
                    eligible += 1
                    units_total += len(units)
                    unsupported = unsupported_standalone_syntax(units)
                    if unsupported:
                        replay_fallback += 1
                        replay_fallback_units += len(units)
                        record["replay_fallback_reason"] = (
                            "unsupported standalone syntax: " + ", ".join(unsupported)
                        )
                        record["sequential"] = {
                            "supported": False,
                            "not_attempted_reason": record["replay_fallback_reason"],
                        }
                        output.write(
                            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                        )
                        continue
                    record["replay_eligible"] = True
                    replay_eligible += 1
                    try:
                        current_state, unavailable = ensure_root(
                            active,
                            env,
                            proposal.theorem_name,
                            str(proposal.record["theorem_statement"]),
                        )
                    except ReplTimeout as error:
                        root_timeouts += 1
                        record["sequential"] = {"timed_out": True, "error": str(error)}
                        stop_client()
                        output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                        continue
                    except ReplError as error:
                        root_errors += 1
                        record["sequential"] = {"timed_out": False, "error": str(error)}
                        stop_client()
                        output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                        continue

                    if current_state is None:
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
                        sequential_complete = False
                        sequential_match = sequential_complete == verdict
                        sequential_matches += int(sequential_match)
                        sequential_disagreements += int(not sequential_match)
                        record["sequential"] = {
                            "complete": sequential_complete,
                            "verdict_match": sequential_match,
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

                    replay_available = True
                    replay_supported = True
                    replay_fallback_reason: str | None = None
                    last_goals: list[Any] | None = None
                    for depth, (edge, unit) in enumerate(
                        zip(edges, units, strict=True), start=1
                    ):
                        reachability = "reached" if replay_available else "unreachable_after_failure"
                        if replay_available:
                            reached_units += 1
                        else:
                            unreachable_units += 1
                        step: dict[str, Any] = {
                            "depth": depth,
                            "prefix_sha256": _prefix_hash(proposal.theorem_name, edges[:depth]),
                            "edge_sha256": hashlib.sha256(edge.encode("utf-8")).hexdigest(),
                            "syntax_kind": unit["syntaxKind"],
                            "reachability": reachability,
                        }
                        if not replay_available:
                            step["not_attempted_reason"] = "prior exact unit failed or timed out"
                            record["steps"].append(step)
                            continue
                        try:
                            replay = active.proof_step(
                                current_state,
                                str(unit["text"]),
                                decl_name=proposal.theorem_name,
                            )
                            replayed_units += 1
                            replay_wall += replay.wall_seconds
                            if replay.cpu_seconds is not None:
                                replay_cpu += replay.cpu_seconds
                            heartbeats = heartbeat_count(replay.response)
                            if heartbeats is not None:
                                heartbeat_total += heartbeats
                            goals = replay.response.get("goals")
                            step_success = proof_step_succeeded(replay.response)
                            if requires_runtime_fallback(replay.response):
                                replay_supported = False
                                replay_fallback_reason = AUXILIARY_DECLARATION_ERROR
                            step.update(
                                {
                                    **_result_metrics(replay),
                                    "heartbeats": heartbeats,
                                    "success": step_success,
                                    "error": replay.response.get("message"),
                                    "goals_after": len(goals) if isinstance(goals, list) else None,
                                }
                            )
                            if step_success:
                                current_state = int(replay.response["proofState"])
                                last_goals = goals if isinstance(goals, list) else None
                            else:
                                replay_available = False
                        except ReplTimeout as error:
                            replay_timeouts += 1
                            step.update({"timed_out": True, "error": str(error)})
                            stop_client()
                            replay_available = False
                        except ReplError as error:
                            replay_errors += 1
                            step.update({"timed_out": False, "error": str(error)})
                            stop_client()
                            replay_available = False
                        record["steps"].append(step)

                    if not replay_supported:
                        replay_eligible -= 1
                        replay_fallback += 1
                        replay_fallback_units += len(units)
                        record["replay_eligible"] = False
                        record["replay_fallback_reason"] = replay_fallback_reason
                        record["sequential"] = {
                            "supported": False,
                            "not_attempted_reason": replay_fallback_reason,
                            "reached_units_before_fallback": sum(
                                step["reachability"] == "reached"
                                for step in record["steps"]
                            ),
                        }
                        output.write(
                            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                        )
                        continue

                    sequential_complete = bool(units and replay_available and last_goals == [])
                    sequential_match = sequential_complete == verdict
                    sequential_matches += int(sequential_match)
                    sequential_disagreements += int(not sequential_match)
                    record["sequential"] = {
                        "complete": sequential_complete,
                        "verdict_match": sequential_match,
                        "reached_units": sum(
                            step["reachability"] == "reached" for step in record["steps"]
                        ),
                        "unreachable_units": sum(
                            step["reachability"] == "unreachable_after_failure"
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
        "analysis": "reached-tactic-cost-profile-v1",
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
            "verdict_disagreements": selected - verdict_matches - full_timeouts - full_errors,
            "full_timeouts": full_timeouts,
            "full_errors": full_errors,
            "native_units": units_total,
            "reached_units": reached_units,
            "unreachable_after_failure": unreachable_units,
            "unreachable_invalid_root": invalid_root_units,
            "sequential_verdict_matches": sequential_matches,
            "sequential_verdict_disagreements": sequential_disagreements,
            "root_timeouts": root_timeouts,
            "root_errors": root_errors,
            "root_unavailable": root_unavailable,
            "replayed_units": replayed_units,
            "replay_timeouts": replay_timeouts,
            "replay_errors": replay_errors,
            "successful_replay_heartbeats": heartbeat_total,
        },
        "timing": {
            "wall_seconds": elapsed,
            "full_request_wall_seconds": full_wall,
            "full_request_cpu_seconds": full_cpu,
            "replay_request_wall_seconds": replay_wall,
            "replay_request_cpu_seconds": replay_cpu,
            "root_setup_wall_seconds": root_wall,
            "root_setup_cpu_seconds": root_cpu,
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
            "lean_toolchain": (lean_workspace / "lean-toolchain").read_text(encoding="utf-8").strip(),
            "lean_version": _capture(["lake", "env", "lean", "--version"], cwd=lean_workspace),
        },
        "artifact": {
            "path": str(output_artifact_path.resolve()),
            "sha256": _sha256_file(output_artifact_path),
            "bytes": output_artifact_path.stat().st_size,
        },
    }
