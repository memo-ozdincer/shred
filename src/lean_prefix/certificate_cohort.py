"""Measured exact-final-syntax cohorts from immutable D-030 paired results."""

from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
from typing import Any, Iterable


MINIMUM_PROPOSALS = 128
MINIMUM_THEOREMS = 10
MINIMUM_HITS = 32
TARGET_AGGREGATE_SPEEDUP = 1.5
TARGET_MEDIAN_THEOREM_SPEEDUP = 1.25
TARGET_P10_THEOREM_SPEEDUP = 1.0
EXPECTED_REPRESENTATIVE_PROPOSALS = 4096
EXPECTED_REPRESENTATIVE_THEOREMS = 128


class CertificateCohortError(RuntimeError):
    """Raised when frozen paired evidence cannot support the cohort analysis."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    cwd = Path.cwd().resolve()
    return str(path.relative_to(cwd)) if path.is_relative_to(cwd) else str(path)


def _git_state(root: Path) -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return {"commit": commit, "dirty": dirty}


def _jsonl(path: Path) -> Iterable[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise CertificateCohortError(
                    f"invalid JSON at {path}:{line_number}: {error}"
                ) from error
            if not isinstance(row, dict):
                raise CertificateCohortError(
                    f"{path}:{line_number} must contain one JSON object"
                )
            yield row


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "minimum": None,
            "p10": None,
            "median": None,
            "p90": None,
            "maximum": None,
        }
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "minimum": ordered[0],
        "p10": ordered[int(0.10 * (len(ordered) - 1))],
        "median": statistics.median(ordered),
        "p90": ordered[int(0.90 * (len(ordered) - 1))],
        "maximum": ordered[-1],
    }


def analyze_certificate_cohorts(
    native_inputs: Path,
    result_artifacts: list[Path],
    parent_report: Path,
    *,
    expected_representative_proposals: int = EXPECTED_REPRESENTATIVE_PROPOSALS,
    expected_representative_theorems: int = EXPECTED_REPRESENTATIVE_THEOREMS,
) -> dict[str, Any]:
    """Join frozen representative measurements by exact final native syntax kind."""
    native_inputs = native_inputs.resolve()
    artifacts = sorted(path.resolve() for path in result_artifacts)
    parent_report = parent_report.resolve()
    if not native_inputs.is_file():
        raise CertificateCohortError(f"missing native input artifact: {native_inputs}")
    if not artifacts or any(not path.is_file() for path in artifacts):
        raise CertificateCohortError("result artifacts must be nonempty existing files")
    if len(set(artifacts)) != len(artifacts):
        raise CertificateCohortError("result artifacts must be unique")
    if not parent_report.is_file():
        raise CertificateCohortError(f"missing parent D-030 report: {parent_report}")
    try:
        parent = json.loads(parent_report.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CertificateCohortError("invalid parent D-030 report") from error
    if (
        not isinstance(parent, dict)
        or parent.get("analysis") != "closing-certificate-prevalence-summary-v1"
    ):
        raise CertificateCohortError("unexpected parent D-030 report identity")
    parent_representative = parent.get("strata", {}).get("representative", {})
    if (
        parent_representative.get("proposals")
        != expected_representative_proposals
        or parent_representative.get("theorems")
        != expected_representative_theorems
    ):
        raise CertificateCohortError("parent D-030 representative counts disagree")

    final_kinds: dict[str, str] = {}
    for row in _jsonl(native_inputs):
        proposal_id = row.get("proposal_id")
        if not isinstance(proposal_id, str) or not proposal_id:
            raise CertificateCohortError("native input lacks proposal_id")
        if proposal_id in final_kinds:
            raise CertificateCohortError(f"duplicate native proposal {proposal_id}")
        units = row.get("units")
        if not isinstance(units, list):
            raise CertificateCohortError(f"invalid native units for {proposal_id}")
        if units:
            syntax_kind = units[-1].get("syntaxKind")
            if not isinstance(syntax_kind, str) or not syntax_kind:
                raise CertificateCohortError(
                    f"missing final native syntax kind for {proposal_id}"
                )
        else:
            syntax_kind = "__no_native_final_unit__"
        final_kinds[proposal_id] = syntax_kind

    representative: list[dict[str, Any]] = []
    seen_results: set[str] = set()
    for path in artifacts:
        for row in _jsonl(path):
            if row.get("stratum") != "representative":
                continue
            proposal_id = row.get("proposal_id")
            if not isinstance(proposal_id, str) or proposal_id not in final_kinds:
                raise CertificateCohortError(
                    f"result has unknown proposal_id {proposal_id!r}"
                )
            if proposal_id in seen_results:
                raise CertificateCohortError(
                    f"duplicate representative result {proposal_id}"
                )
            seen_results.add(proposal_id)
            representative.append({**row, "final_syntax_kind": final_kinds[proposal_id]})

    representative_theorems = {
        str(row.get("theorem_name")) for row in representative
    }
    if len(representative) != expected_representative_proposals:
        raise CertificateCohortError(
            "representative result count does not match frozen D-030"
        )
    if len(representative_theorems) != expected_representative_theorems:
        raise CertificateCohortError(
            "representative theorem count does not match frozen D-030"
        )

    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in representative:
        by_kind[str(row["final_syntax_kind"])].append(row)

    cohorts = []
    for syntax_kind in sorted(by_kind):
        rows = by_kind[syntax_kind]
        event_counts = Counter(
            str(event.get("event"))
            for row in rows
            for event in row["cached"].get("events", [])
        )
        baseline_cpu = sum(float(row["baseline"]["cpu_seconds"]) for row in rows)
        cached_cpu = sum(float(row["cached"]["cpu_seconds"]) for row in rows)
        disagreements = sum(
            bool(row["baseline"]["complete"]) != bool(row["cached"]["complete"])
            for row in rows
        )
        theorem_costs: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for row in rows:
            theorem = str(row["theorem_name"])
            theorem_costs[theorem][0] += float(row["baseline"]["cpu_seconds"])
            theorem_costs[theorem][1] += float(row["cached"]["cpu_seconds"])
        theorem_speedups = [
            baseline / cached
            for baseline, cached in theorem_costs.values()
            if baseline > 0 and cached > 0
        ]
        eligible = (
            len(rows) >= MINIMUM_PROPOSALS
            and len(theorem_costs) >= MINIMUM_THEOREMS
            and event_counts["hit"] >= MINIMUM_HITS
        )
        aggregate_speedup = baseline_cpu / cached_cpu if cached_cpu > 0 else None
        theorem_distribution = _distribution(theorem_speedups)
        passes = (
            eligible
            and disagreements == 0
            and aggregate_speedup is not None
            and aggregate_speedup >= TARGET_AGGREGATE_SPEEDUP
            and theorem_distribution["median"] is not None
            and theorem_distribution["median"] >= TARGET_MEDIAN_THEOREM_SPEEDUP
            and theorem_distribution["p10"] is not None
            and theorem_distribution["p10"] >= TARGET_P10_THEOREM_SPEEDUP
        )
        cohorts.append(
            {
                "final_syntax_kind": syntax_kind,
                "proposals": len(rows),
                "theorems": len(theorem_costs),
                "automatic_hits": event_counts["hit"],
                "event_counts": dict(sorted(event_counts.items())),
                "baseline_cpu_seconds": baseline_cpu,
                "cached_cpu_seconds": cached_cpu,
                "aggregate_cpu_speedup": aggregate_speedup,
                "verdict_disagreements": disagreements,
                "per_theorem_cpu_speedup": theorem_distribution,
                "eligible": eligible,
                "passes_measured_headline_gate": passes,
            }
        )

    eligible_cohorts = [row for row in cohorts if row["eligible"]]
    passing_cohorts = [
        row for row in eligible_cohorts if row["passes_measured_headline_gate"]
    ]
    aggregate_only = [
        row
        for row in eligible_cohorts
        if row["aggregate_cpu_speedup"] is not None
        and row["aggregate_cpu_speedup"] >= TARGET_AGGREGATE_SPEEDUP
        and not row["passes_measured_headline_gate"]
    ]
    if passing_cohorts:
        decision = "measured_natural_final_tactic_cohort_found"
    elif aggregate_only:
        decision = "heterogeneous_aggregate_only_no_headline"
    else:
        decision = "stop_d030_final_tactic_cohort_mining"
    best_eligible_aggregate = (
        max(
            eligible_cohorts,
            key=lambda row: float(row["aggregate_cpu_speedup"] or 0.0),
        )
        if eligible_cohorts
        else None
    )
    return {
        "analysis": "d030-exact-final-syntax-kind-cohorts-v1",
        "evidence_label": "Measured",
        "decision": decision,
        "claim_boundary": (
            "Existing frozen representative paired measurements grouped only by "
            "exact Lean-native final syntax kind; no new Lean execution"
        ),
        "configuration": {
            "stratum": "representative",
            "minimum_proposals": MINIMUM_PROPOSALS,
            "minimum_theorems": MINIMUM_THEOREMS,
            "minimum_automatic_hits": MINIMUM_HITS,
            "target_aggregate_cpu_speedup": TARGET_AGGREGATE_SPEEDUP,
            "target_median_theorem_speedup": TARGET_MEDIAN_THEOREM_SPEEDUP,
            "target_p10_theorem_speedup": TARGET_P10_THEOREM_SPEEDUP,
        },
        "provenance": {
            "analysis_git": _git_state(Path.cwd()),
            "parent_report": {
                "path": _display_path(parent_report),
                "sha256": _sha256(parent_report),
            },
            "parent_d030_provenance": parent.get("provenance"),
        },
        "accounting": {
            "representative_proposals": len(representative),
            "representative_theorems": len(representative_theorems),
            "syntax_kind_cohorts": len(cohorts),
            "eligible_cohorts": len(eligible_cohorts),
            "passing_cohorts": len(passing_cohorts),
            "aggregate_only_cohorts": len(aggregate_only),
        },
        "passing_cohorts": passing_cohorts,
        "aggregate_only_cohorts": aggregate_only,
        "best_eligible_aggregate": (
            {
                "final_syntax_kind": best_eligible_aggregate["final_syntax_kind"],
                "aggregate_cpu_speedup": best_eligible_aggregate[
                    "aggregate_cpu_speedup"
                ],
                "median_theorem_cpu_speedup": best_eligible_aggregate[
                    "per_theorem_cpu_speedup"
                ]["median"],
                "p10_theorem_cpu_speedup": best_eligible_aggregate[
                    "per_theorem_cpu_speedup"
                ]["p10"],
            }
            if best_eligible_aggregate is not None
            else None
        ),
        "eligible_cohorts": eligible_cohorts,
        "all_cohorts": cohorts,
        "inputs": {
            "native_inputs": {
                "path": _display_path(native_inputs),
                "sha256": _sha256(native_inputs),
            },
            "result_artifacts": [
                {"path": _display_path(path), "sha256": _sha256(path)}
                for path in artifacts
            ],
        },
    }
