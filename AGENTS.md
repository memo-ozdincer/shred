# Agent Operating Contract

## Governing claim

This repository tests one mechanism:

```text
independent execution of complete Lean proof attempts
    -> exact shared-prefix-trie execution of those same attempts
```

The input proofs, Lean environment, theorem statements, tactics, timeouts, and
final Lean acceptance rule remain unchanged. The intervention may avoid
repeating an exact prefix; it may not change what is submitted or what Lean
accepts.

## Non-negotiable invariants

- Ordinary Lean remains the correctness authority.
- Return exactly one attributable verdict for every input proposal.
- Count cached, shared, failed, timed-out, and fallback proposals explicitly.
- Never call tactic-head similarity, textual resemblance, or matching proof
  modes an executable prefix match.
- Version one shares only an exact prefix from the same root environment and
  theorem. It does not merge later states reached by different prefixes.
- Unsupported syntax falls back to independent verification; it is never
  silently excluded.
- Source rollout data is read-only and must never be rewritten in place.
- Raw rollout data, credentials, and cluster authentication material must not
  be committed or uploaded.
- Performance claims require identical inputs and verdict agreement against a
  warm independent-execution baseline.
- Report aggregate, median, tail, and per-theorem results. Never rely on a
  favorable global average alone.

## Evidence discipline

Label statements as one of:

- **Measured**: reproduced by a checked-in command with an immutable manifest.
- **Observed**: directly inspected but not yet reproduced by repository code.
- **Hypothesis**: proposed explanation or expected outcome.
- **Decision**: recorded choice with its evidence and consequences.

Do not promote an observation or hypothesis to a measured result.

## Required work order

1. Reproduce the frozen C0 proposal, theorem, correctness, and padding counts.
2. Freeze the source manifest and checksums without copying raw data into Git.
3. Define Lean-native tactic boundaries; heuristic line splitting is not
   authoritative.
4. Measure exact whole-proof and exact prefix reuse offline.
5. Hand-read stratified examples, including successes, failures, long proofs,
   structured tactics, duplicate proofs, and apparent high-reuse theorems.
6. Measure the actual cost of shared and divergent prefixes with per-tactic
   telemetry.
7. Pass the documented feasibility gate before building the execution engine.
8. Implement and freeze the warm independent-execution reference baseline.
9. Implement the smallest exact prefix-trie executor with explicit fallback.
10. Prove verdict equivalence, attribution, isolation, timeout, and accounting
    properties before performance comparisons.
11. Benchmark on authentic rollouts and a held-out workload.

## Scope controls

Version one excludes semantic state merging, cross-theorem reuse, approximate
matching, tactic invention, proof search changes, GPU acceleration, distributed
serving, persistent global caching, and RL algorithm changes. Record attractive
extensions in `docs/FUTURE.md`; do not smuggle them into the primary claim.

## Reporting

Every experiment must save:

- Git commit and dirty status;
- complete command and resolved configuration;
- Lean, Mathlib, dataset, and manifest revisions;
- hardware, concurrency, timeout, and memory limits;
- proposal and theorem counts;
- parser eligibility and fallback counts;
- verdict agreement and disagreements;
- independent, unique-prefix, cached, timed-out, and completed work counts;
- wall time, CPU time, peak memory, throughput, median, p90, p95, and p99;
- raw result paths and SHA-256 checksums.

Record scientific or architectural choices in `docs/DECISIONS.md` before they
become implicit dependencies.

