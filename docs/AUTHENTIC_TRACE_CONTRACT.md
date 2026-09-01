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

## Producer checklist

The manifest freezes dataset, producer Git/dirty state, complete producer
command and resolved configuration digest, Lean/Mathlib revisions, hardware,
concurrency, timeout, memory, expected attempt count, partition hashes, and
telemetry semantics. Each record returns exactly one attributable verdict and
either a fully specified exact checkpoint identity or an explicit fallback.

Unsupported records are never discarded. Partition counts, total attempts,
duplicate proposal IDs, digest conflicts, missing CPU, invalid verdicts, and
prefix CPU greater than complete CPU are fatal validation errors.
