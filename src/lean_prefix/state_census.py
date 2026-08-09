"""Authentic visible-state diagnostics for a possible proof-state DAG.

Pretty-printed goals are observations, not complete Lean-state identities.  The
resulting grouping is therefore an upper bound and never an executable cache
key or correctness claim.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import platform
import time
from typing import Any, Iterable, Iterator, Sequence

from lean_prefix.native import deterministic_gzip_text
from lean_prefix.profile import (
    C0_BASE_CONTEXT,
    _git_state,
    _prefix_hash,
    _sha256_file,
    c0_verifier_declaration,
    lean_complete,
)
from lean_prefix.repl import LeanRepl, ReplError, ReplTimeout
from lean_prefix.review import iter_joined_records


class StateCensusError(RuntimeError):
    """Raised when visible-state evidence cannot be aligned exactly."""


def _records(paths: Iterable[Path]) -> Iterator[dict[str, Any]]:
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else Path.open
        mode = "rt" if path.suffix == ".gz" else "r"
        with opener(path, mode=mode, encoding="utf-8") as stream:
            for line in stream:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise StateCensusError(f"non-object record in {path}")
                yield value


def ordered_tactic_alignment(
    expected: Sequence[str], observed: Sequence[str]
) -> tuple[str, list[int]]:
    """Find one unique ordered alignment, rejecting ambiguous subsequences."""
    if not expected:
        return "unique", []
    normalized_expected = [value.strip() for value in expected]
    normalized_observed = [value.strip() for value in observed]
    states: dict[int, tuple[int, tuple[int, ...] | None]] = {
        index: (1, (index,))
        for index, value in enumerate(normalized_observed)
        if value == normalized_expected[0]
    }
    if not states:
        return "absent", []
    for wanted in normalized_expected[1:]:
        next_states: dict[int, tuple[int, tuple[int, ...] | None]] = {}
        for index, value in enumerate(normalized_observed):
            if value != wanted:
                continue
            predecessors = [item for prior, item in states.items() if prior < index]
            count = min(2, sum(item_count for item_count, _ in predecessors))
            if count == 1:
                path = next(path for item_count, path in predecessors if item_count == 1)
                assert path is not None
                next_states[index] = (1, path + (index,))
            elif count > 1:
                next_states[index] = (2, None)
        states = next_states
        if not states:
            return "absent", []
    count = min(2, sum(item_count for item_count, _ in states.values()))
    if count != 1:
        return "ambiguous", []
    path = next(path for item_count, path in states.values() if item_count == 1)
    assert path is not None
    return "unique", list(path)


def select_edge_opportunity_theorems(
    artifact_paths: list[Path], *, limit: int
) -> dict[str, Any]:
    if limit < 1:
        raise StateCensusError("selection limit must be positive")
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for record in _records(artifact_paths):
        theorem = str(record["theorem_name"])
        for step in record.get("steps", []):
            cpu = step.get("cpu_seconds")
            if step.get("reachability") == "reached" and isinstance(cpu, (int, float)):
                groups[(theorem, str(step["edge_sha256"]))].append(float(cpu))
    by_theorem: Counter[str] = Counter()
    for (theorem, _), values in groups.items():
        by_theorem[theorem] += sum(values) - sum(values) / len(values)
    selected = sorted(by_theorem.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return {
        "analysis": "visible-state-census-selection-v1",
        "selection_rule": (
            "largest exact-edge-within-theorem mean-representative CPU upper bound"
        ),
        "warning": "selection is intentionally high-opportunity and not representative",
        "limit": limit,
        "selected": [
            {"rank": rank, "theorem_name": theorem, "upper_bound_cpu_seconds": value}
            for rank, (theorem, value) in enumerate(selected, start=1)
        ],
        "inputs": {str(path): _sha256_file(path) for path in artifact_paths},
        "revisions": {
            "project_git": _git_state(artifact_paths[0].resolve().parents[2]),
        },
    }


def capture_visible_states(
    manifest_path: Path,
    native_artifact_path: Path,
    output_artifact_path: Path,
    *,
    theorem_name: str,
    lean_workspace: Path,
    source_root: Path | None = None,
    timeout_seconds: float = 300.0,
    memory_limit_bytes: int | None = 48 * 1024**3,
    repl_executable: Path | None = None,
) -> dict[str, Any]:
    """Capture authentic pre-tactic visible goals for one theorem's proposals."""
    if timeout_seconds <= 0:
        raise StateCensusError("timeout must be positive")
    if memory_limit_bytes is not None and memory_limit_bytes <= 0:
        raise StateCensusError("memory limit must be positive")
    started = time.monotonic()
    options: dict[str, Any] = {
        "timeout_seconds": timeout_seconds,
        "memory_limit_bytes": memory_limit_bytes,
    }
    if repl_executable is not None:
        options["executable"] = repl_executable.resolve()
    client = LeanRepl(lean_workspace, **options)
    selected = aligned = fallbacks = timeouts = errors = completed = 0
    try:
        client.start()
        initialization = client.initialize(C0_BASE_CONTEXT)
        if any(
            message.get("severity") == "error"
            for message in initialization.response.get("messages", [])
        ):
            raise StateCensusError("failed to initialize pinned Lean environment")
        env = initialization.response.get("env")
        if not isinstance(env, int):
            raise StateCensusError("initialization returned no environment")
        with deterministic_gzip_text(output_artifact_path) as output:
            for proposal, native in iter_joined_records(
                manifest_path, native_artifact_path, source_root
            ):
                if proposal.theorem_name != theorem_name:
                    continue
                selected += 1
                record: dict[str, Any] = {
                    "proposal_id": proposal.proposal_id,
                    "theorem_name": proposal.theorem_name,
                    "candidate_index": proposal.candidate_index,
                    "expected_correct": proposal.correct,
                    "full": None,
                    "alignment": None,
                    "steps": [],
                }
                declaration = c0_verifier_declaration(
                    str(proposal.record["theorem_statement"]), proposal.proof
                )
                code = "failed to parse" if declaration is None else declaration
                try:
                    result = client.elaborate(code, env=env, all_tactics=True)
                    verdict = lean_complete(result.response)
                    completed += int(verdict)
                    tactics = result.response.get("tactics", [])
                    if not isinstance(tactics, list):
                        raise StateCensusError("Lean returned non-list tactic metadata")
                    record["full"] = {
                        "complete": verdict,
                        "c0_parse_failed": declaration is None,
                        "c0_verdict_match": verdict == proposal.correct,
                        "cpu_seconds": result.cpu_seconds,
                        "wall_seconds": result.wall_seconds,
                    }
                    units = native.get("units", [])
                    edges = native.get("exact_edges")
                    if declaration is None or not native.get("eligible") or edges is None:
                        record["alignment"] = {
                            "status": "fallback",
                            "reason": "parse failure or no authoritative native boundaries",
                        }
                        fallbacks += 1
                    else:
                        expected = [str(unit["text"]) for unit in units]
                        observed = [str(tactic.get("tactic", "")) for tactic in tactics]
                        status, indices = ordered_tactic_alignment(expected, observed)
                        if status != "unique":
                            record["alignment"] = {
                                "status": "fallback",
                                "reason": f"{status} exact ordered tactic alignment",
                            }
                            fallbacks += 1
                        else:
                            record["alignment"] = {"status": "aligned"}
                            aligned += 1
                            for depth, (edge, unit, index) in enumerate(
                                zip(edges, units, indices, strict=True), start=1
                            ):
                                tactic = tactics[index]
                                visible_goal = str(tactic.get("goals", ""))
                                record["steps"].append({
                                    "depth": depth,
                                    "prefix_sha256": _prefix_hash(
                                        proposal.theorem_name, edges[:depth]
                                    ),
                                    "edge_sha256": hashlib.sha256(
                                        edge.encode("utf-8")
                                    ).hexdigest(),
                                    "syntax_kind": str(unit["syntaxKind"]),
                                    "tactic_text": str(unit["text"]),
                                    "visible_goal": visible_goal,
                                    "visible_goal_sha256": hashlib.sha256(
                                        visible_goal.encode("utf-8")
                                    ).hexdigest(),
                                    "position": tactic.get("pos"),
                                    "end_position": tactic.get("endPos"),
                                })
                except ReplTimeout as error:
                    timeouts += 1
                    record["full"] = {"timed_out": True, "error": str(error)}
                    record["alignment"] = {
                        "status": "fallback",
                        "reason": "authentic state capture timed out",
                    }
                    fallbacks += 1
                    client.close()
                    client.start()
                    initialization = client.initialize(C0_BASE_CONTEXT)
                    env = initialization.response.get("env")
                    if not isinstance(env, int):
                        raise StateCensusError("restart returned no environment")
                except ReplError as error:
                    errors += 1
                    record["full"] = {"error": str(error)}
                    record["alignment"] = {
                        "status": "fallback",
                        "reason": "authentic state capture process failure",
                    }
                    fallbacks += 1
                    client.close()
                    client.start()
                    initialization = client.initialize(C0_BASE_CONTEXT)
                    env = initialization.response.get("env")
                    if not isinstance(env, int):
                        raise StateCensusError("restart returned no environment")
                output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    finally:
        client.close()
    if selected == 0:
        raise StateCensusError(f"theorem not found: {theorem_name}")
    return {
        "analysis": "authentic-visible-state-census-v1",
        "theorem_name": theorem_name,
        "warning": "visible goals omit hidden elaborator state and are not cache keys",
        "counts": {
            "selected_proposals": selected,
            "completed": completed,
            "aligned": aligned,
            "fallbacks": fallbacks,
            "timeouts": timeouts,
            "errors": errors,
        },
        "configuration": {
            "timeout_seconds": timeout_seconds,
            "memory_limit_bytes": memory_limit_bytes,
            "all_tactics": True,
        },
        "inputs": {
            "manifest_sha256": _sha256_file(manifest_path),
            "native_artifact_sha256": _sha256_file(native_artifact_path),
        },
        "revisions": {
            "project_git": _git_state(manifest_path.resolve().parent.parent),
            "lean_workspace_git": _git_state(lean_workspace.resolve()),
        },
        "hardware": {"hostname": platform.node()},
        "timing": {"wall_seconds": time.monotonic() - started},
        "artifact": {
            "path": str(output_artifact_path.resolve()),
            "sha256": _sha256_file(output_artifact_path),
        },
    }


def _oracle(groups: dict[Any, list[float]]) -> float:
    return sum(sum(values) - sum(values) / len(values) for values in groups.values())


def summarize_visible_state_census(
    state_artifact_paths: list[Path], replay_artifact_paths: list[Path]
) -> dict[str, Any]:
    """Join authentic visible goals to D019 costs and score reconvergence."""
    state_records: dict[str, dict[str, Any]] = {}
    for record in _records(state_artifact_paths):
        proposal_id = str(record["proposal_id"])
        if proposal_id in state_records:
            raise StateCensusError(f"duplicate state proposal: {proposal_id}")
        state_records[proposal_id] = record
    replay: dict[str, dict[str, Any]] = {}
    for record in _records(replay_artifact_paths):
        proposal_id = str(record["proposal_id"])
        if proposal_id in state_records:
            if proposal_id in replay:
                raise StateCensusError(f"duplicate replay proposal: {proposal_id}")
            replay[proposal_id] = record
    missing = sorted(set(state_records) - set(replay))
    if missing:
        raise StateCensusError(f"missing replay costs for {len(missing)} state proposals")

    full_cpu = 0.0
    verdict_disagreements = aligned = fallbacks = joined_steps = 0
    prefix_groups: dict[str, list[float]] = defaultdict(list)
    state_edge_groups: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    state_prefixes: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    state_kinds: dict[tuple[str, str, str], str] = {}
    for proposal_id, state in state_records.items():
        cost = replay[proposal_id]
        state_full = state.get("full") or {}
        cost_full = cost.get("full") or {}
        if "complete" in state_full and "complete" in cost_full:
            verdict_disagreements += int(state_full["complete"] != cost_full["complete"])
        cpu = cost_full.get("cpu_seconds")
        if isinstance(cpu, (int, float)):
            full_cpu += float(cpu)
        if (state.get("alignment") or {}).get("status") != "aligned":
            fallbacks += 1
            continue
        aligned += 1
        cost_steps = {int(step["depth"]): step for step in cost.get("steps", [])}
        for step in state.get("steps", []):
            measured = cost_steps.get(int(step["depth"]))
            if (
                not measured
                or measured.get("reachability") != "reached"
                or not isinstance(measured.get("cpu_seconds"), (int, float))
            ):
                continue
            if measured.get("edge_sha256") != step.get("edge_sha256"):
                raise StateCensusError(f"edge mismatch for {proposal_id}")
            value = float(measured["cpu_seconds"])
            prefix = str(step["prefix_sha256"])
            key = (
                str(state["theorem_name"]),
                str(step["visible_goal_sha256"]),
                str(step["edge_sha256"]),
            )
            prefix_groups[prefix].append(value)
            state_edge_groups[key].append(value)
            state_prefixes[key].add(prefix)
            state_kinds[key] = str(step["syntax_kind"])
            joined_steps += 1
    if verdict_disagreements:
        raise StateCensusError(
            f"state capture changed {verdict_disagreements} D019 verdicts"
        )
    prefix_saved = _oracle(prefix_groups)
    state_saved = _oracle(state_edge_groups)
    reconvergent = {
        key: values
        for key, values in state_edge_groups.items()
        if len(state_prefixes[key]) > 1
    }
    by_kind: Counter[str] = Counter()
    for key, values in reconvergent.items():
        by_kind[state_kinds[key]] += sum(values) - sum(values) / len(values)
    return {
        "analysis": "visible-state-convergence-summary-v1",
        "status": "diagnostic-only",
        "warning": (
            "Exact pretty-printed goals do not include hidden Lean state; this is an "
            "upper bound, not an executable cache or performance claim."
        ),
        "counts": {
            "proposals": len(state_records),
            "aligned_proposals": aligned,
            "fallback_proposals": fallbacks,
            "joined_reached_steps": joined_steps,
            "visible_state_edge_groups": len(state_edge_groups),
            "reconvergent_groups": len(reconvergent),
        },
        "cpu_seconds": {
            "full_verification": full_cpu,
            "exact_prefix_saved": prefix_saved,
            "visible_state_edge_saved": state_saved,
            "increment_beyond_prefix": state_saved - prefix_saved,
            "visible_state_edge_fraction_full": state_saved / full_cpu if full_cpu else None,
            "increment_beyond_prefix_fraction_full": (
                (state_saved - prefix_saved) / full_cpu if full_cpu else None
            ),
        },
        "reconvergent_savings_by_syntax_kind": by_kind.most_common(),
        "inputs": {
            "state_artifacts": {
                str(path): _sha256_file(path) for path in state_artifact_paths
            },
            "replay_artifacts": {
                str(path): _sha256_file(path) for path in replay_artifact_paths
            },
        },
    }
