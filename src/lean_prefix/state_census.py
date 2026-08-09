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
    artifact_paths: list[Path], *, limit: int, project_root: Path | None = None
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
            "project_git": _git_state((project_root or Path.cwd()).resolve()),
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
        with deterministic_gzip_text(output_artifact_path) as output:
            for proposal, native in iter_joined_records(
                manifest_path, native_artifact_path, source_root
            ):
                if proposal.theorem_name != theorem_name:
                    continue
                # allTactics records ProofSnapshots in the REPL state.  A
                # fresh process per proposal prevents retained metadata from
                # changing later candidates' memory limit or failure mode.
                client.close()
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
                except ReplError as error:
                    errors += 1
                    record["full"] = {"error": str(error)}
                    record["alignment"] = {
                        "status": "fallback",
                        "reason": "authentic state capture process failure",
                    }
                    fallbacks += 1
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
            "restart_every_proposals": 1,
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


def _capture_provenance(
    report_paths: list[Path], state_artifact_paths: list[Path], proposal_count: int
) -> dict[str, Any] | None:
    """Validate and consolidate the per-theorem capture reports."""
    if not report_paths:
        return None
    artifact_hashes = {_sha256_file(path) for path in state_artifact_paths}
    reports: list[dict[str, Any]] = []
    reported_hashes: set[str] = set()
    for path in report_paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("analysis") != "authentic-visible-state-census-v1":
            raise StateCensusError(f"unexpected capture report: {path}")
        artifact_hash = str((value.get("artifact") or {}).get("sha256", ""))
        if not artifact_hash or artifact_hash in reported_hashes:
            raise StateCensusError(f"missing or duplicate capture artifact hash: {path}")
        reported_hashes.add(artifact_hash)
        reports.append(value)
    if reported_hashes != artifact_hashes:
        raise StateCensusError("capture reports do not match state artifacts exactly")
    selected = sum(int(report["counts"]["selected_proposals"]) for report in reports)
    if selected != proposal_count:
        raise StateCensusError(
            f"capture reports account for {selected}, expected {proposal_count} proposals"
        )
    configurations = {
        json.dumps(report["configuration"], sort_keys=True, separators=(",", ":"))
        for report in reports
    }
    project_revisions = {
        json.dumps(
            report["revisions"]["project_git"], sort_keys=True, separators=(",", ":")
        )
        for report in reports
    }
    lean_revisions = {
        json.dumps(
            report["revisions"]["lean_workspace_git"],
            sort_keys=True,
            separators=(",", ":"),
        )
        for report in reports
    }
    if len(configurations) != 1 or len(project_revisions) != 1 or len(lean_revisions) != 1:
        raise StateCensusError("capture reports have mixed configurations or revisions")
    return {
        "reports": len(reports),
        "configuration": json.loads(next(iter(configurations))),
        "revisions": {
            "project_git": json.loads(next(iter(project_revisions))),
            "lean_workspace_git": json.loads(next(iter(lean_revisions))),
        },
        "hardware": sorted({str(report["hardware"]["hostname"]) for report in reports}),
        "counts": {
            name: sum(int(report["counts"][name]) for report in reports)
            for name in (
                "selected_proposals",
                "completed",
                "aligned",
                "fallbacks",
                "timeouts",
                "errors",
            )
        },
        "timing": {
            "maximum_worker_wall_seconds": max(
                float(report["timing"]["wall_seconds"]) for report in reports
            ),
            "sum_worker_wall_seconds": sum(
                float(report["timing"]["wall_seconds"]) for report in reports
            ),
        },
        "theorems": sorted(
            (
                {
                    "theorem_name": str(report["theorem_name"]),
                    "counts": report["counts"],
                    "wall_seconds": float(report["timing"]["wall_seconds"]),
                    "artifact_sha256": str(report["artifact"]["sha256"]),
                }
                for report in reports
            ),
            key=lambda item: item["theorem_name"],
        ),
        "report_sha256": {str(path): _sha256_file(path) for path in report_paths},
    }


def summarize_visible_state_census(
    state_artifact_paths: list[Path],
    replay_artifact_paths: list[Path],
    state_report_paths: list[Path] | None = None,
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
    verdict_comparisons = verdict_disagreements = 0
    aligned = fallbacks = joined_steps = 0
    prefix_groups: dict[str, list[float]] = defaultdict(list)
    state_edge_groups: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    state_prefixes: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    state_kinds: dict[tuple[str, str, str], str] = {}
    state_occurrences: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    closing_prefix_groups: dict[str, list[float]] = defaultdict(list)
    closing_prefix_kinds: dict[str, str] = {}
    closing_state_groups: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    closing_state_prefixes: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    closing_state_kinds: dict[tuple[str, str, str], str] = {}
    closing_occurrences = 0
    for proposal_id, state in state_records.items():
        cost = replay[proposal_id]
        state_full = state.get("full") or {}
        cost_full = cost.get("full") or {}
        if "complete" in state_full and "complete" in cost_full:
            verdict_comparisons += 1
            verdict_disagreements += int(state_full["complete"] != cost_full["complete"])
        cpu = cost_full.get("cpu_seconds")
        if isinstance(cpu, (int, float)):
            full_cpu += float(cpu)
        if (state.get("alignment") or {}).get("status") != "aligned":
            fallbacks += 1
            continue
        aligned += 1
        cost_steps = {int(step["depth"]): step for step in cost.get("steps", [])}
        state_steps = state.get("steps", [])
        final_depth = max((int(step["depth"]) for step in state_steps), default=None)
        for step in state_steps:
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
            state_occurrences[key].append({
                "proposal_id": proposal_id,
                "candidate_index": int(state["candidate_index"]),
                "depth": int(step["depth"]),
                "prefix_sha256": prefix,
                "cpu_seconds": value,
                "tactic_text": str(step["tactic_text"]),
                "visible_goal": str(step["visible_goal"]),
            })
            if state_full.get("complete") is True and int(step["depth"]) == final_depth:
                closing_prefix_groups[prefix].append(value)
                closing_prefix_kinds[prefix] = str(step["syntax_kind"])
                closing_state_groups[key].append(value)
                closing_state_prefixes[key].add(prefix)
                closing_state_kinds[key] = str(step["syntax_kind"])
                closing_occurrences += 1
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
    top_groups: list[dict[str, Any]] = []
    for key in reconvergent:
        occurrences = state_occurrences[key]
        values = [float(item["cpu_seconds"]) for item in occurrences]
        per_prefix: dict[str, list[float]] = defaultdict(list)
        for item in occurrences:
            per_prefix[str(item["prefix_sha256"])].append(float(item["cpu_seconds"]))
        visible_saved = sum(values) - sum(values) / len(values)
        exact_saved = _oracle(per_prefix)
        goal = str(occurrences[0]["visible_goal"])
        top_groups.append({
            "theorem_name": key[0],
            "visible_goal_sha256": key[1],
            "edge_sha256": key[2],
            "syntax_kind": state_kinds[key],
            "tactic_text": str(occurrences[0]["tactic_text"]),
            "visible_goal_characters": len(goal),
            "visible_goal_preview": goal[:1000],
            "occurrences": len(occurrences),
            "distinct_prefixes": len(per_prefix),
            "visible_state_saved_cpu_seconds": visible_saved,
            "exact_prefix_saved_cpu_seconds": exact_saved,
            "increment_beyond_prefix_cpu_seconds": visible_saved - exact_saved,
            "members": [
                {name: item[name] for name in (
                    "proposal_id", "candidate_index", "depth", "prefix_sha256", "cpu_seconds"
                )}
                for item in sorted(
                    occurrences,
                    key=lambda item: (
                        int(item["candidate_index"]), int(item["depth"]), str(item["proposal_id"])
                    ),
                )
            ],
        })
    top_groups.sort(
        key=lambda item: (
            -float(item["increment_beyond_prefix_cpu_seconds"]),
            -float(item["visible_state_saved_cpu_seconds"]),
            str(item["theorem_name"]),
            str(item["visible_goal_sha256"]),
            str(item["edge_sha256"]),
        )
    )

    closing_prefix_saved = _oracle(closing_prefix_groups)
    closing_state_saved = _oracle(closing_state_groups)
    closing_reconvergent = {
        key: values
        for key, values in closing_state_groups.items()
        if len(closing_state_prefixes[key]) > 1
    }
    closing_by_kind: Counter[str] = Counter()
    closing_prefix_by_kind: Counter[str] = Counter()
    for key, values in closing_state_groups.items():
        closing_by_kind[closing_state_kinds[key]] += (
            sum(values) - sum(values) / len(values)
        )
    for prefix, values in closing_prefix_groups.items():
        closing_prefix_by_kind[closing_prefix_kinds[prefix]] += (
            sum(values) - sum(values) / len(values)
        )
    closing_kind_rows = []
    for kind, saved in closing_by_kind.most_common():
        exact_saved = closing_prefix_by_kind[kind]
        closing_kind_rows.append({
            "syntax_kind": kind,
            "visible_state_saved_cpu_seconds": saved,
            "exact_prefix_saved_cpu_seconds": exact_saved,
            "increment_beyond_prefix_cpu_seconds": saved - exact_saved,
        })
    capture = _capture_provenance(
        state_report_paths or [], state_artifact_paths, len(state_records)
    )
    return {
        "analysis": "visible-state-convergence-summary-v1",
        "status": "diagnostic-only",
        "warning": (
            "Exact pretty-printed goals do not include hidden Lean state; this is an "
            "upper bound, not an executable cache or performance claim."
        ),
        "counts": {
            "proposals": len(state_records),
            "verdict_comparisons": verdict_comparisons,
            "verdict_disagreements": verdict_disagreements,
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
        "closing_tactic_diagnostic": {
            "warning": (
                "A closing tactic's generated proof still requires elaboration and kernel "
                "checking; these values are opportunity upper bounds, not saved CPU."
            ),
            "counts": {
                "occurrences": closing_occurrences,
                "visible_state_edge_groups": len(closing_state_groups),
                "reconvergent_groups": len(closing_reconvergent),
            },
            "cpu_seconds": {
                "exact_prefix_saved": closing_prefix_saved,
                "visible_state_edge_saved": closing_state_saved,
                "increment_beyond_prefix": closing_state_saved - closing_prefix_saved,
                "visible_state_edge_fraction_full": (
                    closing_state_saved / full_cpu if full_cpu else None
                ),
                "increment_beyond_prefix_fraction_full": (
                    (closing_state_saved - closing_prefix_saved) / full_cpu
                    if full_cpu else None
                ),
            },
            "savings_by_syntax_kind": closing_kind_rows,
        },
        "reconvergent_savings_by_syntax_kind": by_kind.most_common(),
        "top_reconvergent_groups": top_groups[:20],
        "capture_provenance": capture,
        "inputs": {
            "state_artifacts": {
                str(path): _sha256_file(path) for path in state_artifact_paths
            },
            "replay_artifacts": {
                str(path): _sha256_file(path) for path in replay_artifact_paths
            },
        },
    }
