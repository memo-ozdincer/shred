"""Bounded exact checkpoint-branch proof-of-mechanism probe.

This is a controlled mechanism test authorized by D-033.  It is not a corpus
benchmark and its deliberately expensive prefix is not an authentic workload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time
from typing import Any, Iterable

from lean_prefix.native import deterministic_gzip_text
from lean_prefix.profile import C0_BASE_CONTEXT, lean_complete, theorem_root_code, theorem_root_outcome
from lean_prefix.repl import LeanRepl, ReplResult


ANALYSIS_ID = "exact-checkpoint-branch-probe-v1"
THEOREM_NAME = "shred_branch_probe"
EXPONENT = 500
BASE = 12345
SUFFIXES = (
    "trivial",
    "exact True.intro",
    "constructor",
    "simp",
    "norm_num",
    "decide",
    "omega",
    "aesop",
    "exact ⟨⟩",
    "apply True.intro",
    "rfl",
    "assumption",
    "exact Nat.zero",
    "apply False.elim",
    "change False",
    "exact And.intro True.intro True.intro",
)


class BranchProbeError(RuntimeError):
    """Raised when the bounded fork probe violates an invariant."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_state(path: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(path), *args], text=True, stderr=subprocess.DEVNULL
        ).strip()

    try:
        status = run("status", "--porcelain")
        return {"commit": run("rev-parse", "HEAD"), "dirty": bool(status)}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def _metrics(result: ReplResult) -> dict[str, Any]:
    return {
        "wall_seconds": result.wall_seconds,
        "cpu_seconds": result.cpu_seconds,
        "peak_rss_kib": result.peak_rss_kib,
    }


def _step_verdict(result: ReplResult) -> bool:
    errors = [
        message for message in result.response.get("messages", [])
        if message.get("severity") == "error"
    ]
    return not errors and result.response.get("goals") == []


def _next_state(result: ReplResult, label: str) -> int:
    errors = [
        message for message in result.response.get("messages", [])
        if message.get("severity") == "error"
    ]
    state = result.response.get("proofState")
    if errors or not isinstance(state, int) or result.response.get("goals") == []:
        raise BranchProbeError(f"{label} did not yield a reusable nonterminal proof state")
    return state


def _sum_metric(records: Iterable[dict[str, Any]], field: str) -> float | None:
    values = [record[field] for record in records]
    if any(value is None for value in values):
        return None
    return sum(float(value) for value in values)


def _quantiles(records: list[dict[str, Any]], field: str) -> dict[str, float] | None:
    values = sorted(float(record[field]) for record in records if record[field] is not None)
    if len(values) != len(records) or not values:
        return None

    def at(fraction: float) -> float:
        return values[int(fraction * (len(values) - 1))]

    return {
        "minimum": values[0],
        "median": at(0.50),
        "p90": at(0.90),
        "p95": at(0.95),
        "p99": at(0.99),
        "maximum": values[-1],
    }


def summarize_timings(
    shared_prefix: dict[str, Any],
    shared_suffixes: list[dict[str, Any]],
    independent_prefixes: list[dict[str, Any]],
    independent_suffixes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize paired prefix/suffix request timings without hiding overhead."""
    if not shared_suffixes or len(shared_suffixes) != len(independent_suffixes):
        raise BranchProbeError("shared and independent suffix counts must match and be nonzero")
    if len(independent_prefixes) != len(independent_suffixes):
        raise BranchProbeError("every independent suffix must have its own prefix execution")

    output: dict[str, Any] = {"branches": len(shared_suffixes)}
    for metric in ("wall_seconds", "cpu_seconds"):
        shared_suffix_total = _sum_metric(shared_suffixes, metric)
        independent_prefix_total = _sum_metric(independent_prefixes, metric)
        independent_suffix_total = _sum_metric(independent_suffixes, metric)
        shared_prefix_value = shared_prefix[metric]
        if None in (
            shared_suffix_total,
            independent_prefix_total,
            independent_suffix_total,
            shared_prefix_value,
        ):
            output[metric.removesuffix("_seconds")] = None
            continue
        independent_total = float(independent_prefix_total) + float(independent_suffix_total)
        shared_total = float(shared_prefix_value) + float(shared_suffix_total)
        output[metric.removesuffix("_seconds")] = {
            "independent_prefix_seconds": independent_prefix_total,
            "independent_suffix_seconds": independent_suffix_total,
            "independent_total_seconds": independent_total,
            "shared_prefix_seconds": shared_prefix_value,
            "shared_suffix_seconds": shared_suffix_total,
            "shared_total_seconds": shared_total,
            "independent_prefix_fraction": (
                float(independent_prefix_total) / independent_total
                if independent_total > 0 else None
            ),
            "measured_speedup": independent_total / shared_total if shared_total > 0 else None,
        }
    return output


def run_probe(
    *,
    lean_workspace: Path,
    repl_executable: Path,
    artifact_path: Path,
    report_path: Path,
    timeout_seconds: float = 300.0,
    memory_limit_gib: float = 16.0,
) -> dict[str, Any]:
    if len(SUFFIXES) > 16:
        raise BranchProbeError("D-033 permits at most 16 suffixes")
    if artifact_path.exists() or report_path.exists():
        raise BranchProbeError("refusing to overwrite an existing probe output")

    value = BASE**EXPONENT
    prefix = f"have h : ({BASE} : Nat) ^ {EXPONENT} = {value} := by norm_num"
    statement = f"theorem {THEOREM_NAME} : True := by"
    started = time.monotonic()
    records: list[dict[str, Any]] = []

    with LeanRepl(
        lean_workspace,
        executable=repl_executable,
        timeout_seconds=timeout_seconds,
        memory_limit_bytes=int(memory_limit_gib * 1024**3),
    ) as repl:
        initialization = repl.initialize(C0_BASE_CONTEXT)
        env = initialization.response.get("env")
        if not isinstance(env, int):
            raise BranchProbeError("base initialization did not return an environment")
        root = repl.elaborate(theorem_root_code(statement), env=env)
        root_state, root_failure = theorem_root_outcome(THEOREM_NAME, root.response)
        if root_state is None or root_failure is not None:
            raise BranchProbeError(f"theorem root unavailable: {root_failure}")

        # Shared first makes subsequent independent prefix executions warm.  Any
        # cache-order effect is therefore conservative against the shared path.
        shared_prefix_result = repl.proof_step(
            root_state, prefix, count_heartbeats=False, decl_name=THEOREM_NAME
        )
        shared_state = _next_state(shared_prefix_result, "shared prefix")
        shared_suffix_metrics: list[dict[str, Any]] = []
        shared_verdicts: list[bool] = []
        for index, suffix in enumerate(SUFFIXES):
            result = repl.proof_step(
                shared_state, suffix, count_heartbeats=False, decl_name=THEOREM_NAME
            )
            verdict = _step_verdict(result)
            metrics = _metrics(result)
            shared_suffix_metrics.append(metrics)
            shared_verdicts.append(verdict)
            records.append({
                "candidate_index": index,
                "candidate_id": hashlib.sha256(suffix.encode()).hexdigest(),
                "mode": "shared_suffix",
                "suffix": suffix,
                "verdict": verdict,
                **metrics,
            })

        independent_prefix_metrics: list[dict[str, Any]] = []
        independent_suffix_metrics: list[dict[str, Any]] = []
        independent_verdicts: list[bool] = []
        for index, suffix in enumerate(SUFFIXES):
            prefix_result = repl.proof_step(
                root_state, prefix, count_heartbeats=False, decl_name=THEOREM_NAME
            )
            candidate_state = _next_state(prefix_result, f"independent prefix {index}")
            suffix_result = repl.proof_step(
                candidate_state, suffix, count_heartbeats=False, decl_name=THEOREM_NAME
            )
            verdict = _step_verdict(suffix_result)
            prefix_metrics = _metrics(prefix_result)
            suffix_metrics = _metrics(suffix_result)
            independent_prefix_metrics.append(prefix_metrics)
            independent_suffix_metrics.append(suffix_metrics)
            independent_verdicts.append(verdict)
            records.append({
                "candidate_index": index,
                "candidate_id": hashlib.sha256(suffix.encode()).hexdigest(),
                "mode": "independent_root_replay",
                "suffix": suffix,
                "verdict": verdict,
                "prefix": prefix_metrics,
                "suffix_metrics": suffix_metrics,
            })

        complete_verdicts: list[bool] = []
        complete_metrics: list[dict[str, Any]] = []
        for index, suffix in enumerate(SUFFIXES):
            unique_name = f"{THEOREM_NAME}_complete_{index}"
            declaration = (
                f"theorem {unique_name} : True := by\n"
                f"  {prefix}\n"
                f"  {suffix}\n"
            )
            result = repl.elaborate(declaration, env=env)
            verdict = lean_complete(result.response)
            metrics = _metrics(result)
            complete_verdicts.append(verdict)
            complete_metrics.append(metrics)
            records.append({
                "candidate_index": index,
                "candidate_id": hashlib.sha256(suffix.encode()).hexdigest(),
                "mode": "ordinary_complete_proof",
                "suffix": suffix,
                "verdict": verdict,
                **metrics,
            })

    disagreements = [
        index for index, verdicts in enumerate(
            zip(shared_verdicts, independent_verdicts, complete_verdicts, strict=True)
        ) if len(set(verdicts)) != 1
    ]
    if disagreements:
        raise BranchProbeError(f"verdict disagreement for candidates {disagreements}")

    artifact_text = "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    with deterministic_gzip_text(artifact_path) as artifact:
        artifact.write(artifact_text)
    timing = summarize_timings(
        _metrics(shared_prefix_result),
        shared_suffix_metrics,
        independent_prefix_metrics,
        independent_suffix_metrics,
    )
    timing["request_latency_distributions"] = {
        "shared_suffix_wall_seconds": _quantiles(shared_suffix_metrics, "wall_seconds"),
        "shared_suffix_cpu_seconds": _quantiles(shared_suffix_metrics, "cpu_seconds"),
        "independent_prefix_wall_seconds": _quantiles(
            independent_prefix_metrics, "wall_seconds"
        ),
        "independent_prefix_cpu_seconds": _quantiles(
            independent_prefix_metrics, "cpu_seconds"
        ),
        "independent_suffix_wall_seconds": _quantiles(
            independent_suffix_metrics, "wall_seconds"
        ),
        "independent_suffix_cpu_seconds": _quantiles(
            independent_suffix_metrics, "cpu_seconds"
        ),
        "ordinary_complete_proof_wall_seconds": _quantiles(
            complete_metrics, "wall_seconds"
        ),
        "ordinary_complete_proof_cpu_seconds": _quantiles(
            complete_metrics, "cpu_seconds"
        ),
    }
    timing["per_theorem"] = [{
        "theorem": THEOREM_NAME,
        "branches": len(SUFFIXES),
        "cpu_speedup": timing["cpu"]["measured_speedup"] if timing["cpu"] else None,
        "wall_speedup": timing["wall"]["measured_speedup"] if timing["wall"] else None,
    }]
    report = {
        "analysis": ANALYSIS_ID,
        "evidence_label": "Measured controlled mechanism probe",
        "claim_boundary": (
            "Not an authentic workload, prevalence estimate, dataset speedup, or RL pipeline result"
        ),
        "command": (
            "python -m lean_prefix.branch_probe "
            f"--lean-workspace {lean_workspace} --repl-executable {repl_executable} "
            f"--artifact {artifact_path} --output {report_path} "
            f"--timeout-seconds {timeout_seconds} --memory-limit-gib {memory_limit_gib}"
        ),
        "configuration": {
            "base": BASE,
            "exponent": EXPONENT,
            "prefix_sha256": hashlib.sha256(prefix.encode()).hexdigest(),
            "branches": len(SUFFIXES),
            "timeout_seconds": timeout_seconds,
            "memory_limit_gib": memory_limit_gib,
            "execution_order": "shared_then_independent_then_complete",
        },
        "counts": {
            "proposals": len(SUFFIXES),
            "accepted": sum(complete_verdicts),
            "rejected": len(SUFFIXES) - sum(complete_verdicts),
            "shared_verdict_disagreements": sum(
                left != right for left, right in zip(shared_verdicts, complete_verdicts)
            ),
            "independent_verdict_disagreements": sum(
                left != right for left, right in zip(independent_verdicts, complete_verdicts)
            ),
            "fallbacks": 0,
            "timeouts": 0,
            "errors": 0,
        },
        "timing": timing,
        "non_benchmark_costs": {
            "initialization": _metrics(initialization),
            "root_setup": _metrics(root),
            "ordinary_complete_proof_total_wall_seconds": sum(
                item["wall_seconds"] for item in complete_metrics
            ),
            "total_probe_wall_seconds": time.monotonic() - started,
        },
        "provenance": {
            "project_git": _git_state(Path.cwd()),
            "lean_workspace_git": _git_state(lean_workspace),
            "repl_executable": str(repl_executable.resolve()),
            "repl_sha256": _sha256_file(repl_executable),
            "hardware": {
                "hostname": platform.node(),
                "platform": platform.platform(),
                "cpu_count": os.cpu_count(),
            },
        },
        "artifact": {
            "path": str(artifact_path),
            "sha256": _sha256_file(artifact_path),
            "records": len(records),
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lean-workspace", type=Path, required=True)
    parser.add_argument("--repl-executable", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--memory-limit-gib", type=float, default=16.0)
    args = parser.parse_args(argv)
    report = run_probe(
        lean_workspace=args.lean_workspace,
        repl_executable=args.repl_executable,
        artifact_path=args.artifact,
        report_path=args.output,
        timeout_seconds=args.timeout_seconds,
        memory_limit_gib=args.memory_limit_gib,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
