"""Frozen, paired prevalence measurement for automatic closing certificates."""

from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import platform
import re
import statistics
import time
from typing import Any, Iterable, Iterator

from lean_prefix.native import deterministic_gzip_text, proof_body
from lean_prefix.profile import C0_BASE_CONTEXT, c0_verifier_declaration, lean_complete, _git_state
from lean_prefix.repl import LeanRepl, ReplError, ReplTimeout
from lean_prefix.review import iter_joined_records


class CertificatePrevalenceError(RuntimeError):
    """Raised when selection, instrumentation, or paired accounting is unsafe."""


SELECTION_SEED = "closing-certificate-prevalence-d026-v1"
CERTIFICATE_CONTEXT = C0_BASE_CONTEXT.replace(
    "import Mathlib\nimport Aesop\n",
    "import LeanPrefix.AutomaticCertificate\nimport Aesop\n",
    1,
).replace(
    "open BigOperators Real Nat Topology Rat\n",
    "open BigOperators Real Nat Topology Rat\nopen LeanPrefix.AutomaticCertificate\n",
    1,
)
_EVENT = re.compile(r"LEAN_PREFIX_CERT event=(?P<event>[a-z_]+)(?: (?P<fields>.*))?")
CACHE_EXCLUDED_SYNTAX = frozenset({"Lean.Parser.Tactic.tacticRfl"})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _records(paths: Iterable[Path]) -> Iterator[dict[str, Any]]:
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else Path.open
        mode = "rt" if path.suffix == ".gz" else "r"
        with opener(path, mode=mode, encoding="utf-8") as stream:
            for line in stream:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise CertificatePrevalenceError(f"non-object record in {path}")
                yield value


def _rank(theorem_name: str) -> str:
    return hashlib.sha256(f"{SELECTION_SEED}\0{theorem_name}".encode()).hexdigest()


def select_certificate_prevalence_theorems(
    replay_paths: list[Path],
    *,
    representative_count: int = 128,
    enriched_count: int = 32,
    project_root: Path | None = None,
) -> dict[str, Any]:
    if representative_count < 1 or enriched_count < 1:
        raise CertificatePrevalenceError("selection counts must be positive")
    theorems: set[str] = set()
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    proposals = 0
    for record in _records(replay_paths):
        proposals += 1
        theorem = str(record["theorem_name"])
        theorems.add(theorem)
        full = record.get("full") or {}
        steps = record.get("steps") or []
        if full.get("complete") is not True or not steps:
            continue
        final = max(steps, key=lambda step: int(step["depth"]))
        cpu = final.get("cpu_seconds")
        if final.get("reachability") == "reached" and isinstance(cpu, (int, float)):
            groups[(theorem, str(final["edge_sha256"]))].append(float(cpu))
    representative = sorted(theorems, key=lambda theorem: (_rank(theorem), theorem))[
        :representative_count
    ]
    representative_set = set(representative)
    opportunity: Counter[str] = Counter()
    occurrences: Counter[str] = Counter()
    for (theorem, _), values in groups.items():
        if len(values) < 2:
            continue
        opportunity[theorem] += sum(values) - sum(values) / len(values)
        occurrences[theorem] += len(values)
    enriched_candidates = [
        theorem for theorem in opportunity if theorem not in representative_set
    ]
    enriched = sorted(
        enriched_candidates,
        key=lambda theorem: (-opportunity[theorem], theorem),
    )[:enriched_count]
    if len(representative) != representative_count or len(enriched) != enriched_count:
        raise CertificatePrevalenceError("not enough theorems for frozen strata")
    return {
        "analysis": "closing-certificate-prevalence-selection-v1",
        "warning": (
            "the representative stratum is an unweighted deterministic theorem sample; "
            "the enriched stratum is mechanism-seeking and cannot estimate prevalence"
        ),
        "seed": SELECTION_SEED,
        "counts": {
            "source_proposals": proposals,
            "source_theorems": len(theorems),
            "representative_theorems": len(representative),
            "enriched_theorems": len(enriched),
        },
        "representative": [
            {"rank": index, "theorem_name": theorem, "selection_sha256": _rank(theorem)}
            for index, theorem in enumerate(representative, 1)
        ],
        "enriched": [
            {
                "rank": index,
                "theorem_name": theorem,
                "repeated_final_edge_upper_bound_cpu_seconds": opportunity[theorem],
                "repeated_final_edge_occurrences": occurrences[theorem],
            }
            for index, theorem in enumerate(enriched, 1)
        ],
        "inputs": {str(path): _sha256(path) for path in replay_paths},
        "revisions": {"project_git": _git_state((project_root or Path.cwd()).resolve())},
    }


def prepare_certificate_prevalence_inputs(
    manifest_path: Path,
    native_artifact_path: Path,
    selection_path: Path,
    output_artifact_path: Path,
    *,
    source_root: Path | None = None,
) -> dict[str, Any]:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    strata = {
        str(item["theorem_name"]): name
        for name in ("representative", "enriched")
        for item in selection[name]
    }
    counts: Counter[str] = Counter()
    with deterministic_gzip_text(output_artifact_path) as output:
        for proposal, native in iter_joined_records(
            manifest_path, native_artifact_path, source_root
        ):
            stratum = strata.get(proposal.theorem_name)
            if stratum is None:
                continue
            counts[stratum] += 1
            output.write(json.dumps({
                "stratum": stratum,
                "proposal_id": proposal.proposal_id,
                "theorem_name": proposal.theorem_name,
                "candidate_index": proposal.candidate_index,
                "expected_correct": proposal.correct,
                "theorem_statement": proposal.record["theorem_statement"],
                "proof": proposal.proof,
                "native_eligible": bool(native.get("eligible")),
                "native_error": native.get("error"),
                "units": native.get("units") or [],
            }, sort_keys=True, separators=(",", ":")) + "\n")
    expected = {
        "representative": len(selection["representative"]) * 32,
        "enriched": len(selection["enriched"]) * 32,
    }
    if dict(counts) != expected:
        raise CertificatePrevalenceError(
            f"prepared counts {dict(counts)} do not match {expected}"
        )
    return {
        "analysis": "closing-certificate-prevalence-inputs-v1",
        "counts": dict(counts),
        "inputs": {
            "manifest": _sha256(manifest_path),
            "native_artifact": _sha256(native_artifact_path),
            "selection": _sha256(selection_path),
        },
        "artifact": {
            "path": str(output_artifact_path.resolve()),
            "sha256": _sha256(output_artifact_path),
        },
    }


def wrap_final_tactic(proof: str, units: list[dict[str, Any]]) -> str | None:
    if not units:
        return None
    body = proof_body(proof)
    source = body.encode("utf-8")
    unit = units[-1]
    start = int(unit["startByte"])
    stop = int(unit["stopByte"])
    if start < 0 or stop < start or stop > len(source):
        raise CertificatePrevalenceError("invalid final tactic byte range")
    tactic = source[start:stop]
    if tactic.decode("utf-8") != str(unit["text"]):
        raise CertificatePrevalenceError("final tactic disagrees with native range")
    line_start = source.rfind(b"\n", 0, start) + 1
    indentation = source[line_start:start]
    if indentation.strip():
        raise CertificatePrevalenceError("final tactic does not begin after indentation")
    nested = indentation + b"  "
    wrapped = b"reuse_closing in\n" + nested + tactic.replace(b"\n", b"\n  ")
    transformed_body = (source[:start] + wrapped + source[stop:]).decode("utf-8")
    return transformed_body + proof[len(body):]


def _events(response: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for message in response.get("messages", []):
        match = _EVENT.search(str(message.get("data", "")))
        if match is None:
            continue
        fields: dict[str, Any] = {"event": match.group("event")}
        for item in (match.group("fields") or "").split():
            if "=" not in item:
                continue
            name, value = item.split("=", 1)
            fields[name] = int(value) if value.isdigit() else value
        events.append(fields)
    return events


def _run_mode(
    rows: list[dict[str, Any]],
    *,
    cached: bool,
    lean_workspace: Path,
    timeout_seconds: float,
    memory_limit_bytes: int | None,
    repl_executable: Path | None,
) -> tuple[list[dict[str, Any]], int]:
    options: dict[str, Any] = {
        "timeout_seconds": timeout_seconds,
        "memory_limit_bytes": memory_limit_bytes,
    }
    if repl_executable is not None:
        options["executable"] = repl_executable.resolve()
    client = LeanRepl(lean_workspace, **options)
    results: list[dict[str, Any]] = []
    resets = 0
    env: int | None = None

    def initialize() -> int:
        nonlocal resets
        client.close()
        client.start()
        initialized = client.initialize(CERTIFICATE_CONTEXT)
        value = initialized.response.get("env")
        if not isinstance(value, int) or not lean_complete(initialized.response):
            raise CertificatePrevalenceError("failed to initialize certificate REPL")
        resets += 1
        return value

    try:
        env = initialize()
        for row in rows:
            proof = str(row["proof"])
            instrumented = False
            exclusion: str | None = None
            final_kind = str(row["units"][-1].get("syntaxKind", "")) if row["units"] else ""
            if cached and final_kind in CACHE_EXCLUDED_SYNTAX:
                exclusion = "registered_rfl_resource_and_cost_fallback"
            elif cached and row["native_eligible"]:
                replacement = wrap_final_tactic(proof, list(row["units"]))
                if replacement is not None:
                    proof = replacement
                    instrumented = True
            declaration = c0_verifier_declaration(str(row["theorem_statement"]), proof)
            code = "failed to parse" if declaration is None else declaration
            result_record: dict[str, Any] = {
                "instrumented": instrumented,
                "instrumentation_exclusion": exclusion,
                "complete": False,
                "timed_out": False,
                "process_error": None,
                "cpu_seconds": None,
                "wall_seconds": None,
                "peak_rss_kib": None,
                "events": [],
            }
            try:
                assert env is not None
                result = client.elaborate(code, env=env)
                events = _events(result.response)
                query_cpu = query_wall = 0.0
                if cached and instrumented:
                    query = client.elaborate("#lean_prefix_certificate_events", env=env)
                    events = _events(query.response)
                    query_cpu = float(query.cpu_seconds or 0.0)
                    query_wall = float(query.wall_seconds)
                result_record.update({
                    "complete": lean_complete(result.response),
                    "cpu_seconds": (
                        float(result.cpu_seconds) + query_cpu
                        if result.cpu_seconds is not None else None
                    ),
                    "wall_seconds": result.wall_seconds + query_wall,
                    "peak_rss_kib": max(
                        value for value in (result.peak_rss_kib, query.peak_rss_kib if cached and instrumented else None)
                        if value is not None
                    ) if result.peak_rss_kib is not None else None,
                    "events": events,
                    "error_messages": [
                        str(message.get("data", ""))[:4000]
                        for message in result.response.get("messages", [])
                        if message.get("severity") == "error"
                    ],
                    "telemetry_query_cpu_seconds": query_cpu,
                    "telemetry_query_wall_seconds": query_wall,
                })
            except ReplTimeout as error:
                result_record.update({
                    "timed_out": True,
                    "cpu_seconds": error.cpu_seconds,
                    "wall_seconds": error.wall_seconds,
                    "peak_rss_kib": error.peak_rss_kib,
                    "process_error": str(error),
                })
                env = initialize()
            except ReplError as error:
                result_record["process_error"] = str(error)
                env = initialize()
            results.append(result_record)
    finally:
        client.close()
    return results, resets


def run_certificate_prevalence_theorem(
    input_artifact_path: Path,
    output_artifact_path: Path,
    *,
    theorem_name: str,
    lean_workspace: Path,
    timeout_seconds: float = 300.0,
    memory_limit_bytes: int | None = 48 * 1024**3,
    repl_executable: Path | None = None,
) -> dict[str, Any]:
    rows = [
        row for row in _records([input_artifact_path])
        if row["theorem_name"] == theorem_name
    ]
    if len(rows) != 32 or [row["candidate_index"] for row in rows] != list(range(32)):
        raise CertificatePrevalenceError(f"{theorem_name} does not have candidates 0..31")
    started = time.monotonic()
    baseline, baseline_resets = _run_mode(
        rows,
        cached=False,
        lean_workspace=lean_workspace,
        timeout_seconds=timeout_seconds,
        memory_limit_bytes=memory_limit_bytes,
        repl_executable=repl_executable,
    )
    cached, cached_resets = _run_mode(
        rows,
        cached=True,
        lean_workspace=lean_workspace,
        timeout_seconds=timeout_seconds,
        memory_limit_bytes=memory_limit_bytes,
        repl_executable=repl_executable,
    )
    with deterministic_gzip_text(output_artifact_path) as output:
        for row, base, cache in zip(rows, baseline, cached, strict=True):
            output.write(json.dumps({
                "stratum": row["stratum"],
                "proposal_id": row["proposal_id"],
                "theorem_name": theorem_name,
                "candidate_index": row["candidate_index"],
                "expected_correct": row["expected_correct"],
                "baseline": base,
                "cached": cache,
            }, sort_keys=True, separators=(",", ":")) + "\n")
    comparisons = sum(1 for base, cache in zip(baseline, cached) if base["complete"] == cache["complete"])
    return {
        "analysis": "closing-certificate-prevalence-theorem-v1",
        "theorem_name": theorem_name,
        "stratum": rows[0]["stratum"],
        "counts": {
            "proposals": len(rows),
            "verdict_agreements": comparisons,
            "verdict_disagreements": len(rows) - comparisons,
            "baseline_resets": baseline_resets,
            "cached_resets": cached_resets,
        },
        "configuration": {
            "timeout_seconds": timeout_seconds,
            "memory_limit_bytes": memory_limit_bytes,
            "same_initialized_environment_per_proposal": True,
            "proposal_order": "candidate_index_ascending",
        },
        "hardware": {"hostname": platform.node()},
        "timing": {"worker_wall_seconds": time.monotonic() - started},
        "inputs": {"prepared_artifact_sha256": _sha256(input_artifact_path)},
        "artifact": {"path": str(output_artifact_path.resolve()), "sha256": _sha256(output_artifact_path)},
        "revisions": {
            "project_git": _git_state(Path.cwd()),
            "lean_workspace_git": _git_state(lean_workspace.resolve()),
        },
    }


def summarize_certificate_prevalence(
    artifact_paths: list[Path], report_paths: list[Path], selection_path: Path | None = None
) -> dict[str, Any]:
    if not artifact_paths or not report_paths:
        raise CertificatePrevalenceError("artifacts and reports are required")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in report_paths]
    reported = {str(report["artifact"]["sha256"]) for report in reports}
    actual = {_sha256(path) for path in artifact_paths}
    if reported != actual or len(reported) != len(report_paths):
        raise CertificatePrevalenceError("theorem reports do not match artifacts exactly")
    project_revisions = {
        json.dumps(report["revisions"]["project_git"], sort_keys=True)
        for report in reports
    }
    lean_revisions = {
        json.dumps(report["revisions"]["lean_workspace_git"], sort_keys=True)
        for report in reports
    }
    configurations = {
        json.dumps(report["configuration"], sort_keys=True)
        for report in reports
    }
    if len(project_revisions) != 1 or len(lean_revisions) != 1 or len(configurations) != 1:
        raise CertificatePrevalenceError("theorem reports mix revisions or configurations")
    records = list(_records(artifact_paths))
    identities = [str(record["proposal_id"]) for record in records]
    if len(identities) != len(set(identities)):
        raise CertificatePrevalenceError("duplicate proposal results")
    by_stratum: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_stratum[str(record["stratum"])].append(record)

    def distribution(values: list[float]) -> dict[str, Any]:
        ordered = sorted(values)
        def quantile(probability: float) -> float:
            return ordered[round((len(ordered) - 1) * probability)]
        return {
            "count": len(ordered),
            "sum": sum(ordered),
            "mean": statistics.fmean(ordered),
            "median": statistics.median(ordered),
            "p90": quantile(0.90),
            "p95": quantile(0.95),
            "p99": quantile(0.99),
            "maximum": ordered[-1],
        }

    def aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
        events = Counter(
            event["event"]
            for item in items
            for event in item["cached"]["events"]
        )
        disagreements = [
            {"proposal_id": item["proposal_id"], "theorem_name": item["theorem_name"], "candidate_index": item["candidate_index"]}
            for item in items
            if item["baseline"]["complete"] != item["cached"]["complete"]
        ]
        baseline_cpu = sum(float(item["baseline"]["cpu_seconds"] or 0.0) for item in items)
        cached_cpu = sum(float(item["cached"]["cpu_seconds"] or 0.0) for item in items)
        instrumented = sum(bool(item["cached"]["instrumented"]) for item in items)
        baseline_values = [float(item["baseline"]["cpu_seconds"] or 0.0) for item in items]
        cached_values = [float(item["cached"]["cpu_seconds"] or 0.0) for item in items]
        saved_values = [base - cache for base, cache in zip(baseline_values, cached_values)]
        return {
            "proposals": len(items),
            "theorems": len({item["theorem_name"] for item in items}),
            "instrumented_closing_tactics": instrumented,
            "event_counts": dict(sorted(events.items())),
            "automatic_hits": events["hit"],
            "hit_fraction_of_instrumented": events["hit"] / instrumented if instrumented else 0.0,
            "baseline_cpu_seconds": baseline_cpu,
            "cached_cpu_seconds": cached_cpu,
            "paired_cpu_saved_seconds": baseline_cpu - cached_cpu,
            "paired_cpu_saved_fraction": (baseline_cpu - cached_cpu) / baseline_cpu if baseline_cpu else 0.0,
            "verdict_agreements": len(items) - len(disagreements),
            "verdict_disagreements": disagreements,
            "baseline_timeouts": sum(bool(item["baseline"]["timed_out"]) for item in items),
            "cached_timeouts": sum(bool(item["cached"]["timed_out"]) for item in items),
            "baseline_process_errors": sum(item["baseline"]["process_error"] is not None for item in items),
            "cached_process_errors": sum(item["cached"]["process_error"] is not None for item in items),
            "baseline_cpu_distribution": distribution(baseline_values),
            "cached_cpu_distribution": distribution(cached_values),
            "paired_cpu_saved_distribution": distribution(saved_values),
        }

    aggregates = {name: aggregate(items) for name, items in sorted(by_stratum.items())}
    representative = aggregates.get("representative")
    if representative is None:
        raise CertificatePrevalenceError("representative stratum is missing")
    completeness: dict[str, Any] | None = None
    if selection_path is not None:
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        expected = {
            name: {str(item["theorem_name"]) for item in selection[name]}
            for name in ("representative", "enriched")
        }
        actual = {
            name: {str(item["theorem_name"]) for item in items}
            for name, items in by_stratum.items()
        }
        completeness = {
            name: {
                "expected_theorems": len(expected[name]),
                "completed_theorems": len(actual.get(name, set())),
                "expected_proposals": 32 * len(expected[name]),
                "completed_proposals": len(by_stratum.get(name, [])),
                "missing_theorems": sorted(expected[name] - actual.get(name, set())),
                "unexpected_theorems": sorted(actual.get(name, set()) - expected[name]),
            }
            for name in ("representative", "enriched")
        }
    representative_complete = (
        completeness is None
        or not completeness["representative"]["missing_theorems"]
        and not completeness["representative"]["unexpected_theorems"]
        and completeness["representative"]["completed_proposals"]
        == completeness["representative"]["expected_proposals"]
    )
    decision = (
        "stop_or_redirect"
        if not representative_complete
        or representative["verdict_disagreements"]
        or representative["paired_cpu_saved_fraction"] < 0.15
        else "advance_minimal_production_cache"
    )
    report: dict[str, Any] = {
        "analysis": "closing-certificate-prevalence-summary-v1",
        "status": (
            "complete"
            if completeness is None or all(
                not value["missing_theorems"] and not value["unexpected_theorems"]
                and value["completed_proposals"] == value["expected_proposals"]
                for value in completeness.values()
            )
            else "complete-representative-incomplete-enriched"
        ),
        "decision_gate": {
            "minimum_representative_cpu_saved_fraction": 0.15,
            "requires_zero_verdict_disagreements": True,
            "outcome": decision,
        },
        "strata": aggregates,
        "counts": {"artifacts": len(artifact_paths), "reports": len(report_paths), "proposals": len(records)},
        "provenance": {
            "theorem_project_git": json.loads(next(iter(project_revisions))),
            "lean_workspace_git": json.loads(next(iter(lean_revisions))),
            "configuration": json.loads(next(iter(configurations)),),
            "summary_project_git": _git_state(Path.cwd()),
            "hardware": sorted({str(report["hardware"]["hostname"]) for report in reports}),
            "maximum_worker_wall_seconds": max(float(report["timing"]["worker_wall_seconds"]) for report in reports),
            "sum_worker_wall_seconds": sum(float(report["timing"]["worker_wall_seconds"]) for report in reports),
        },
        "inputs": {
            "artifact_sha256": {str(path): _sha256(path) for path in artifact_paths},
            "report_sha256": {str(path): _sha256(path) for path in report_paths},
        },
    }
    if completeness is not None:
        report["completeness"] = completeness
        report["inputs"]["selection"] = {
            "path": str(selection_path),
            "sha256": _sha256(selection_path),
        }
    return report
