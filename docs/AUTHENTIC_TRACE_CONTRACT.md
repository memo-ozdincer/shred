# Existing-run checkpoint trace contract

Status: implemented read-only value screener. It does not execute Lean.

## Purpose

`shred screen-authentic-trace` lets an RL system, proof-search service, or repair
agent export telemetry from a run it has already performed and ask whether
portable exact checkpoints are theoretically worth implementing. This removes
the need to adopt SHRED, rerun a benchmark, or expose raw proof text merely to
evaluate the opportunity.

The manifest schema is
`data/authentic-checkpoint-trace.schema.json`. Partitions are immutable JSONL or
JSONL.gz files. Source data remains read-only and may stay outside Git.

## Producer flow

The producer writes one JSON object per attempt to one or more `.jsonl` or
`.jsonl.gz` partitions. It separately records workload metadata, including the
expected attempt count. SHRED can then freeze the hashes and validate the whole
export without rewriting those partitions:

```bash
shred seal-authentic-trace \
  --workload-metadata workload.json \
  --partition worker-000.jsonl.gz \
  --partition worker-001.jsonl.gz \
  --output existing-run.manifest.json
```

The seal operation refuses overwrite, requires the independently declared
attempt count to equal the physical row count, and creates the manifest only
after every record passes the same validation used by the screener. It does not
execute Lean. Workload metadata has this shape:

```json
{
  "name": "grpo-verification-run",
  "dataset_revision": "immutable-dataset-revision",
  "producer_git_commit": "producer-git-commit",
  "producer_git_dirty": false,
  "producer_command": "complete resolved producer command",
  "resolved_configuration_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "lean_revision": "exact Lean revision",
  "mathlib_revision": "exact Mathlib revision",
  "hardware": "CPU model and deployment identity",
  "concurrency": 8,
  "timeout_seconds": 300,
  "memory_limit_bytes": 51539607552,
  "expected_attempts": 800,
  "pipeline_total_cpu_seconds": 12345.6
}
```

`expected_attempts` must come from the producer's run accounting; the sealer
does not infer it and then call that inference complete. Pipeline CPU is needed
for the end-to-end materiality gate.

## Exactness boundary

An `exact_checkpoint` record means the producer captured one Lean-native prefix
from one theorem and root environment. It must provide digests for:

- the unchanged proposal and theorem statement;
- the complete parent environment and root local context;
- the ordered Lean-native prefix edges; and
- the checkpoint artifact itself.

A textual prefix, pretty-printed goal, tactic-head match, reconstructed state,
or common agent conversation is not eligible. Such attempts must be exported as
`fallback` with a reason and retain their complete independent CPU cost.

The telemetry declaration is intentionally rigid: process CPU, a warm complete
independent baseline, prefix CPU measured through the same exact checkpoint,
and ordinary Lean verdict authority. Missing or differently defined telemetry
fails closed instead of being coerced into the contract.

An eligible record contains only digests, attribution, verdict, and cost; raw
proof text need not be exported:

```json
{
  "proposal_id": "run-17/theorem-4/attempt-6",
  "proposal_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "theorem_name": "MyProject.target",
  "theorem_statement_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "verdict": "accepted",
  "full_verifier_cpu_seconds": 1.72,
  "eligibility": "exact_checkpoint",
  "prefix_verifier_cpu_seconds": 1.31,
  "parent_environment_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "root_context_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "prefix_edges_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "checkpoint_artifact_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
}
```

If any exact field is unavailable, the attempt remains present and becomes a
fallback:

```json
{
  "proposal_id": "run-17/theorem-4/attempt-7",
  "proposal_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "theorem_name": "MyProject.target",
  "theorem_statement_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "verdict": "timed_out",
  "full_verifier_cpu_seconds": 300.0,
  "eligibility": "fallback",
  "fallback_reason": "checkpoint_identity_not_recorded"
}
```

## Projection

For each exact group with at least eight attempts, let `f_i` be complete warm
independent verifier CPU and `p_i` be CPU through the shared checkpoint. The
zero-overhead projected group cost is:

```text
max(p_i) + sum(f_i - p_i)
```

Using the maximum observed prefix cost once is conservative against variation
among independent executions. Every suffix, timeout, rejection, crash, and
fallback remains in the denominator. A registered per-hit load/finalization
budget is then added for each of the `n - 1` cache hits.

The frozen value gate additionally requires at least 100 qualifying groups
across at least 10 theorems, at least 60% of all verifier CPU removable by exact
prefix reuse before overhead, registered overhead no greater than 0.2 mean
complete verifications per eight attempts, and verifier CPU at least 25% of
total pipeline CPU. These are applicability constraints, not requests for more
seeds: a smaller authentic workload stops as too narrow rather than authorizing
repetition solely to cross the threshold.

The report includes aggregate CPU, the maximum overhead compatible with the
target, complete verdict and fallback counts, qualifying group details,
per-theorem results, median/p10/p90/p95/p99 theorem speedups, and an end-to-end
Amdahl projection from the manifest's total pipeline CPU.

This is a **Hypothesis** projection from **Observed** producer telemetry. It is
not a measured SHRED result. A passing two-times value gate permits proposing
one bounded paired implementation experiment under D-036; it does not permit a
README speed claim.

## Usage

```bash
shred screen-authentic-trace \
  --manifest existing-run.manifest.json \
  --overhead-budget-cpu-seconds-per-hit 0.01 \
  --overhead-budget-source "registered deployment design ceiling" \
  --output checkpoint-screen.json
```

Omit both overhead arguments to compute only the zero-overhead ceiling. The
decision then remains `inconclusive_missing_registered_overhead_budget`, even
if the ceiling exceeds two-times.

The sealer is also available through the public Python API:

```python
from pathlib import Path
from shred import seal_authentic_trace

receipt = seal_authentic_trace(
    Path("existing-run.manifest.json"),
    workload=workload_metadata,
    partitions=[Path("worker-000.jsonl.gz")],
)
```

## Producer checklist

The manifest freezes dataset, producer Git/dirty state, complete producer
command and resolved configuration digest, Lean/Mathlib revisions, hardware,
concurrency, timeout, memory, expected attempt count, partition hashes, and
telemetry semantics. Each record returns exactly one attributable verdict and
either a fully specified exact checkpoint identity or an explicit fallback.

Unsupported records are never discarded. Partition counts, total attempts,
duplicate proposal IDs, digest conflicts, missing CPU, invalid verdicts, and
prefix CPU greater than complete CPU are fatal validation errors.
