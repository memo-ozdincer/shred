# Exact checkpoint-branch controlled probe

Evidence labels follow `AGENTS.md`. The timings and verdict counts below are
**Measured** by the checked-in D-033 runner. The decision not to broaden this
into synthetic benchmarking is **Decision** D-034.

## Scope

This probe tests whether one exact Lean proof state can safely serve several
unchanged candidate suffixes and whether the resulting cost follows the fork
model. It intentionally constructs a prefix-heavy theorem by proving a large
natural-number normalization fact before leaving the goal `True`. It is not a
sample from an RL, search, repair, or theorem dataset.

The runner executes 16 fixed suffixes in three modes:

1. execute the common prefix once and branch every suffix from its proof state;
2. replay the common prefix independently from the theorem root for every
   suffix;
3. elaborate every complete proof normally through Lean.

Shared execution runs first, so any later process-local warming favors the
independent baseline. Initialization, theorem-root setup, and the correctness
replays are reported separately from the prefix-plus-suffix comparison.

## Result

| Quantity | Measured result |
|---|---:|
| Candidate suffixes | 16 |
| Accepted / rejected | 9 / 7 |
| Shared verdict disagreements | 0 |
| Independent verdict disagreements | 0 |
| Fallbacks / timeouts / errors | 0 / 0 / 0 |
| Independent prefix-plus-suffix CPU | 0.268181 s |
| Shared prefix-plus-suffix CPU | 0.048486 s |
| CPU speedup | **5.531x** |
| Independent prefix-plus-suffix wall | 0.274198 s |
| Shared prefix-plus-suffix wall | 0.050326 s |
| Wall speedup | **5.448x** |
| Independent CPU in common prefixes | 88.49% |

The ordinary complete-proof checks consumed another 0.335582 wall seconds and
are excluded from both sides of the mechanism comparison. Warm Mathlib
initialization consumed 10.199840 wall seconds and is also excluded; a serving
or RL deployment would have to amortize it explicitly.

## Interpretation

**Measured:** the exact checkpoint can be reused across successful and failing
suffixes without changing any of the 16 ordinary Lean verdicts. The measured
5.531x CPU result is consistent with the expected advantage of executing an
88.49%-dominant prefix once instead of 16 times.

**Not measured:** authentic branch frequency, authentic prefix cost share,
throughput under concurrency, cross-process serialization, timeout isolation,
or the fraction of an RL pipeline spent inside Lean. Therefore 5.531x is not a
dataset or end-to-end SHRED claim and must not be placed in the README as one.

**Decision:** stop controlled variants here. The mechanism has cleared its
bounded feasibility question. Further Lean execution requires authentic traces
passing D-034's structural and cost gates.

## Provenance

The aggregate report is `reports/branch_probe_d033.json`. The proposal-level
artifact is `artifacts/branch_probe_d033.jsonl.gz`, SHA-256
`7baad4372ff23e5544d065fb81f487bda9306bfbe965773e47898071eac05146`,
containing 48 records. The report records the project and Lean workspace Git
states, patched REPL checksum, hardware, memory limit, timeout, complete
command, and separated initialization/correctness costs. The aggregate report
SHA-256 is
`9f297bdebcb20c6865b7d941f324229e6e61588c9b6c088f0b598dffa4f97e97`.
