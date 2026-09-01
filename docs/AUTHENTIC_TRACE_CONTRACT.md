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
  "verifier_slots": 135,
  "timeout_seconds": 300,
  "memory_limit_bytes": 51539607552,
  "expected_attempts": 800,
  "pipeline_total_cpu_seconds": 12345.6
}
```

`expected_attempts` must come from the producer's run accounting; the sealer
does not infer it and then call that inference complete. Pipeline CPU is needed
for the end-to-end materiality gate. `verifier_slots` is optional but, when
present, must be the independently resolved maximum number of concurrent Lean
verification jobs for this workload—not GPU count or general pipeline
concurrency. Without it, the report omits the topology-aware service projection.

## Exactness boundary

An `exact_checkpoint` record means the producer captured one Lean-native prefix
from one theorem and root environment. Version two also identifies the live
Lean execution scope that independently ran the complete attempt. It must
provide digests for:

- the unchanged proposal and theorem statement;
- the complete parent environment and root local context;
- the ordered Lean-native prefix edges; and
- the checkpoint artifact itself; and
- the producer-owned execution scope, such as a fresh REPL lease or process.

The scope digest is SHA-256 over a producer-defined, run-unique identity. It
must change when attempts cannot share a live proof state without portable
loading. Worker names, hostnames, and raw UUIDs need not leave the producer.

A textual prefix, pretty-printed goal, tactic-head match, reconstructed state,
or common agent conversation is not eligible. Such attempts must be exported as
`fallback` with a reason and retain their complete independent CPU cost.

If the producer's pre-existing verifier already suppresses an exact duplicate
complete attempt, preserve that input as a fallback with
`baseline_execution: "cached_exact_duplicate"`,
`fallback_reason: "existing_exact_duplicate_cache"`, and zero verifier CPU.
Name the representative proposal. This is existing baseline caching, not SHRED
prefix reuse, and it contributes no claimed opportunity. Any executed attempt
whose exact process-CPU envelope is missing makes the producer export invalid;
it must not be assigned wall time, a sampled CPU percentage, or an inferred
cost merely to make the trace sealable.

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
  "checkpoint_artifact_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "execution_scope_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
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

The version-two screener makes two decisions from the same immutable trace.

For process-local sharing, it partitions each exact checkpoint identity by
execution scope. A scope subgroup qualifies only with at least eight complete
attempts. Its projected cost is the maximum observed prefix CPU once plus every
unchanged suffix. The process-local gate independently requires at least 100
qualifying scope groups across 10 theorems, at least 60% of all verifier CPU
removable before overhead, at least 2x projected verifier throughput, the same
strict overhead limit, and material pipeline verifier CPU. Its registered
per-hit budget is specific to local trie dispatch, snapshot branching, and
accounting; it is not borrowed from the portable loader.

For each exact group with at least eight attempts spanning at least two live
Lean execution scopes, let `f_i` be complete warm independent verifier CPU and
`p_i` be CPU through the shared checkpoint. The zero-overhead projected group
cost is:

```text
max(p_i) + sum(f_i - p_i)
```

Using the maximum observed prefix cost once is conservative against variation
among independent executions. Every suffix, timeout, rejection, crash, and
fallback remains in the denominator. A registered per-hit load/finalization
budget is then added for each of the `n - 1` cache hits.

A qualifying exact group confined to one live scope is reported separately as
process-local fan-out opportunity. It cannot pass the portable-checkpoint gate:
that would confuse an optimization already available to ordinary tactic-tree
search with evidence for reuse across workers or policy iterations.

For a cross-scope group, the screener also computes an ideal process-local
counterfactual: execute the prefix once per scope, using the maximum prefix CPU
observed in that scope. The incremental portable saving is the sum of those
per-scope prefix costs minus the single global maximum. Thus a group split 4+4
across two workers cannot claim all seven avoided prefixes as portable value;
six are available from local sharing and only one is uniquely cross-worker.

The frozen value gate additionally requires at least 100 cross-scope qualifying
groups across at least 10 theorems, at least 60% of all verifier CPU removable
incrementally across scopes after ideal process-local sharing, at least 2x
portable speedup over that process-local counterfactual, registered overhead no
greater than 0.2 mean complete verifications per eight attempts, and verifier
CPU at least 25% of total pipeline CPU. These are applicability constraints,
not requests for more seeds: a smaller authentic workload stops as too narrow
rather than authorizing repetition solely to cross the threshold.

The report includes aggregate CPU, the maximum overhead compatible with the
target, complete verdict and fallback counts, qualifying group details and
scope counts, separately excluded single-scope opportunity, per-theorem
results, the ideal process-local counterfactual, incremental portable saving,
median/p10/p90/p95/p99 theorem speedups for both total and incremental portable
effects, and an end-to-end Amdahl projection from the manifest's total pipeline
CPU.

For qualifying process-local groups, the report also emits a controlled-
replication CPU frontier. For each replica count `k` (capped at each group's
attempt count), it charges each group the lesser of all independently observed
prefix CPU and `k` times the maximum observed prefix CPU, then leaves all suffix
and fallback CPU unchanged.
This is conservative under observed prefix-cost variation, matches the ordinary
one-trie projection at `k = 1`, and returns to independent execution when every
attempt has its own replica. Registered local overhead is charged only to the
remaining `n - k` reused attempts. This frontier makes the CPU cost of exposing
more parallelism directly testable from an existing trace.

When `verifier_slots` is declared, the screener additionally constructs an
achievable CPU-service schedule. Within each group it greedily assigns observed
suffix costs to `k` replicas while charging the maximum observed prefix in each
replica; it then longest-processing-time schedules every resulting replica job,
unchanged nonqualifying attempt, and fallback across the declared slots. The
independent baseline is scheduled by the same rule. This uses actual cost
variation and can test whether a topology headline survives beyond equal-cost
wave arithmetic. It is still not measured wall latency: CPU-service seconds do
not include queueing, communication, or contention. Selecting a latency point
requires authentic wall-time evidence and a pre-registered objective rather
than post-hoc selection of the prettiest multiplier. A frontier point passes
the balanced screen only when a registered overhead is present and the actual-
cost projection simultaneously retains at least 2x CPU throughput and 1.5x
CPU-service makespan improvement.

The top-level recommendation is deliberately singular: choose portable reuse
when its incremental gate passes; otherwise choose the process-local exact trie
when its gate passes; otherwise return inconclusive or stop. A local pass never
becomes portable evidence, and a portable pass never invents eight co-located
attempts that the producer did not execute.

This is a **Hypothesis** projection from **Observed** producer telemetry. It is
not a measured SHRED result. A passing two-times value gate permits proposing
one bounded paired implementation experiment under D-036; it does not permit a
README speed claim.

## Usage

```bash
shred screen-authentic-trace \
  --manifest existing-run.manifest.json \
  --process-local-overhead-budget-cpu-seconds-per-hit 0.002 \
  --process-local-overhead-budget-source "registered trie dispatch ceiling" \
  --portable-overhead-budget-cpu-seconds-per-hit 0.01 \
  --portable-overhead-budget-source "registered checkpoint load ceiling" \
  --output checkpoint-screen.json
```

Each mechanism's amount and source must be supplied together. Omit one pair to
compute that mechanism's zero-overhead ceiling while leaving only that decision
`inconclusive_missing_registered_overhead_budget`. A registered portable budget
never authorizes the local gate, and a local budget never authorizes portability.
The shorter historical `--overhead-budget-*` flags remain aliases for the
portable pair. The Python API likewise retains `overhead_budget_*` as portable-
only aliases and rejects mixing the old and explicit keyword pairs.

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
either a fully specified exact checkpoint plus execution-scope identity or an
explicit fallback.

Unsupported records are never discarded. Partition counts, total attempts,
duplicate proposal IDs, digest conflicts, missing CPU, invalid verdicts, and
prefix CPU greater than complete CPU are fatal validation errors.
