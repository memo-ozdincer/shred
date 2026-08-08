"""Lean-native tactic extraction and exact rooted-prefix analysis."""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time
from typing import Any, Iterator, Sequence

from lean_prefix.corpus import Proposal, iter_proposals
from lean_prefix.prefix import summarize_prefixes


class NativeExtractionError(RuntimeError):
    """Raised when the native parser protocol or result is inconsistent."""


def proof_body(proof: str) -> str:
    return proof.split("```", 1)[0]


def exact_edges(proof: str, units: Sequence[dict[str, Any]]) -> tuple[str, ...]:
    """Recover exact rooted edge text, including inter-tactic trivia.

    Lean reports UTF-8 byte ranges. Each edge begins where the preceding edge
    ended, so whitespace and comments remain part of the exact prefix identity.
    """
    source = proof_body(proof).encode("utf-8")
    previous_stop = 0
    edges: list[str] = []
    for unit in units:
        start = int(unit["startByte"])
        stop = int(unit["stopByte"])
        if start < previous_stop or stop < start or stop > len(source):
            raise NativeExtractionError(
                f"invalid native range start={start} stop={stop} "
                f"previous_stop={previous_stop} source_bytes={len(source)}"
            )
        reported = str(unit["text"]).encode("utf-8")
        if source[start:stop] != reported:
            raise NativeExtractionError("native unit text disagrees with its reported source range")
        edges.append(source[previous_stop:stop].decode("utf-8"))
        previous_stop = stop
    return tuple(edges)


def fallback_class(error: str | None) -> str:
    if not error:
        return "unknown"
    if "top-level semicolon" in error:
        return "top_level_semicolon"
    if "bracketed root" in error:
        return "bracketed_root"
    if "unknown tactic" in error:
        return "unknown_tactic"
    if "unexpected end of input" in error:
        return "unexpected_end"
    if "invalid request" in error:
        return "invalid_request"
    return "parse_or_range_error"


@contextmanager
def deterministic_gzip_text(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8") as text:
                yield text


def _quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * probability)]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _capture(command: list[str], *, cwd: Path | None = None) -> str:
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


def _record_for_artifact(
    proposal: Proposal, response: dict[str, Any], edges: tuple[str, ...] | None
) -> dict[str, Any]:
    return {
        "proposal_id": proposal.proposal_id,
        "theorem_name": proposal.theorem_name,
        "candidate_index": proposal.candidate_index,
        "correct": proposal.correct,
        "proof_sha256": hashlib.sha256(proposal.proof.encode("utf-8")).hexdigest(),
        "eligible": bool(response.get("eligible", False)),
        "error": response.get("error"),
        "units": response.get("units", []),
        "exact_edges": list(edges) if edges is not None else None,
    }


def extract_and_analyze(
    manifest_path: Path,
    *,
    lean_workspace: Path,
    extractor_path: Path,
    artifact_path: Path,
    source_root: Path | None = None,
    limit: int | None = None,
    progress_every: int = 10_000,
) -> dict[str, Any]:
    """Run the pinned Lean parser once and measure exact prefix reuse."""
    if limit is not None and limit < 0:
        raise NativeExtractionError("limit must be non-negative")
    if progress_every < 0:
        raise NativeExtractionError("progress interval must be non-negative")
    manifest_path = manifest_path.resolve()
    extractor_path = extractor_path.resolve()
    lean_workspace = lean_workspace.resolve()
    artifact_path = artifact_path.resolve()
    project_root = manifest_path.parent.parent
    command = ["lake", "env", "lean", "--run", str(extractor_path.resolve())]
    started = time.monotonic()
    self_usage_before = resource.getrusage(resource.RUSAGE_SELF)
    child_usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    process = subprocess.Popen(
        command,
        cwd=lean_workspace,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    if process.stdin is None or process.stdout is None:
        raise NativeExtractionError("failed to open native extractor pipes")

    sequences_by_theorem: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    prefix_counts_by_theorem: dict[str, Counter[tuple[str, ...]]] = defaultdict(Counter)
    sequence_lengths: list[float] = []
    syntax_kinds: Counter[str] = Counter()
    fallbacks: Counter[str] = Counter()
    proposals = eligible = correct = total_units = 0

    try:
        with deterministic_gzip_text(artifact_path) as artifact:
            for proposal in iter_proposals(manifest_path, source_root):
                if limit is not None and proposals >= limit:
                    break
                request = {"proposalId": proposal.proposal_id, "proof": proposal.proof}
                process.stdin.write(json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n")
                process.stdin.flush()
                response_line = process.stdout.readline()
                if not response_line:
                    raise NativeExtractionError(
                        f"native extractor ended before proposal {proposal.proposal_id}"
                    )
                try:
                    response = json.loads(response_line)
                except json.JSONDecodeError as error:
                    raise NativeExtractionError(
                        f"invalid native JSON for proposal {proposal.proposal_id}: {error}"
                    ) from error
                if response.get("proposalId") != proposal.proposal_id:
                    raise NativeExtractionError(
                        f"response identity mismatch for {proposal.proposal_id}: "
                        f"{response.get('proposalId')!r}"
                    )

                proposals += 1
                correct += int(proposal.correct)
                edges: tuple[str, ...] | None = None
                if response.get("eligible"):
                    units = response.get("units")
                    if not isinstance(units, list) or not units:
                        raise NativeExtractionError("eligible response has no tactic units")
                    edges = exact_edges(proposal.proof, units)
                    eligible += 1
                    total_units += len(edges)
                    sequence_lengths.append(float(len(edges)))
                    sequences_by_theorem[proposal.theorem_name].append(edges)
                    counts = prefix_counts_by_theorem[proposal.theorem_name]
                    for depth in range(1, len(edges) + 1):
                        counts[edges[:depth]] += 1
                    syntax_kinds.update(str(unit["syntaxKind"]) for unit in units)
                else:
                    fallbacks[fallback_class(response.get("error"))] += 1

                artifact.write(
                    json.dumps(
                        _record_for_artifact(proposal, response, edges),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                if progress_every and proposals % progress_every == 0:
                    elapsed = time.monotonic() - started
                    print(
                        f"parsed {proposals:,} proposals in {elapsed:.1f}s "
                        f"({proposals / elapsed:.1f}/s)",
                        file=sys.stderr,
                    )
    finally:
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        return_code = process.wait()
        if return_code != 0:
            raise NativeExtractionError(f"native extractor exited with status {return_code}")

    unique_nodes = reusable = 0
    theorem_ratios: list[float] = []
    shared_depths: list[float] = []
    shared_first_proposals = 0
    for theorem, sequences in sequences_by_theorem.items():
        summary = summarize_prefixes(sequences)
        unique_nodes += summary.unique_nodes
        reusable += summary.reusable_step_occurrences
        theorem_ratios.append(summary.oracle_ratio)
        counts = prefix_counts_by_theorem[theorem]
        shared_first_proposals += sum(
            count for prefix, count in counts.items() if len(prefix) == 1 and count >= 2
        )
        for sequence in sequences:
            shared_depth = 0
            for depth in range(1, len(sequence) + 1):
                if counts[sequence[:depth]] < 2:
                    break
                shared_depth = depth
            shared_depths.append(float(shared_depth))

    elapsed = time.monotonic() - started
    self_usage = resource.getrusage(resource.RUSAGE_SELF)
    child_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "analysis": "lean-native-exact-prefix-v1",
        "configuration": {
            "command": command,
            "limit": limit,
            "parser_processes": 1,
            "timeout_seconds": None,
            "memory_limit_bytes": None,
        },
        "revisions": {
            "project_git": _git_state(project_root),
            "manifest_sha256": _sha256_file(manifest_path),
            "extractor_sha256": _sha256_file(extractor_path),
            "lean_workspace_git": _git_state(lean_workspace),
            "lean_toolchain": (lean_workspace / "lean-toolchain").read_text(encoding="utf-8").strip(),
            "lean_version": _capture(["lake", "env", "lean", "--version"], cwd=lean_workspace),
        },
        "hardware": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "logical_cpus_visible": os.cpu_count(),
        },
        "resources": {
            "wall_seconds": elapsed,
            "python_user_cpu_seconds": self_usage.ru_utime - self_usage_before.ru_utime,
            "python_system_cpu_seconds": self_usage.ru_stime - self_usage_before.ru_stime,
            "lean_user_cpu_seconds": child_usage.ru_utime - child_usage_before.ru_utime,
            "lean_system_cpu_seconds": child_usage.ru_stime - child_usage_before.ru_stime,
            "python_peak_rss_kib": self_usage.ru_maxrss,
            "lean_peak_rss_kib": child_usage.ru_maxrss,
        },
        "lean_workspace": str(lean_workspace),
        "extractor": str(extractor_path),
        "proposals": proposals,
        "correct": correct,
        "eligible_proposals": eligible,
        "eligibility_share": eligible / proposals if proposals else 0.0,
        "fallback_proposals": proposals - eligible,
        "fallback_classes": dict(sorted(fallbacks.items())),
        "independent_tactic_units_eligible": total_units,
        "unique_prefix_nodes_eligible": unique_nodes,
        "reusable_tactic_unit_occurrences": reusable,
        "unweighted_prefix_oracle_ratio": total_units / unique_nodes if unique_nodes else 1.0,
        "shared_first_prefix_proposals": shared_first_proposals,
        "shared_first_prefix_share_of_eligible": shared_first_proposals / eligible if eligible else 0.0,
        "sequence_length": {
            "median": _quantile(sequence_lengths, 0.5),
            "p90": _quantile(sequence_lengths, 0.9),
            "p99": _quantile(sequence_lengths, 0.99),
            "max": max(sequence_lengths, default=None),
        },
        "shared_prefix_depth": {
            "median": _quantile(shared_depths, 0.5),
            "p90": _quantile(shared_depths, 0.9),
            "p99": _quantile(shared_depths, 0.99),
            "max": max(shared_depths, default=None),
        },
        "per_theorem_oracle_ratio": {
            "median": _quantile(theorem_ratios, 0.5),
            "p90": _quantile(theorem_ratios, 0.9),
            "p99": _quantile(theorem_ratios, 0.99),
            "max": max(theorem_ratios, default=None),
        },
        "syntax_kinds": dict(syntax_kinds.most_common()),
        "artifact": {
            "path": str(artifact_path.resolve()),
            "sha256": _sha256_file(artifact_path),
            "bytes": artifact_path.stat().st_size,
        },
    }
