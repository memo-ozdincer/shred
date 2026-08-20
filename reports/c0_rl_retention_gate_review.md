# RL closure retention gate review

Date: 2026-08-20 Eastern

Evidence label: **Measured**. The calculation ran from clean commit `8bbcefe`,
verified every registered D019 and D030 artifact hash, and performed no new
Lean, REPL, or cluster execution.

## Result

Twenty-seven of the 505 D-029-admitted theorems were already present in the
frozen D030 automatic-certificate study. Their 864 proposals provide direct
paired evidence for the exact mechanism without spending new compute:

- baseline CPU: 1,396.345 seconds;
- cached CPU: 1,202.358 seconds;
- saved CPU: 193.987 seconds, or 13.892%;
- CPU-equivalent throughput: 1.161x;
- exact automatic hits: 206;
- verdict agreement: 864/864; and
- positive aggregate saving on 26/27 theorems.

The deterministic theorem bootstrap gives a 95% interval of 7.759%--20.258%
CPU saving. The D-030 theory gate requires at least 36.690% realized reusable
CPU for 1.5x throughput. Even the bootstrap upper bound misses that requirement
by 16.432 percentage points, so the failure is decisive under the registered
one-sided rule.

On the same theorem overlap, D019's repeated-final-edge calculation suggested
a 50.837% reuse upper bound. Actual paired D030 saving was only 26.816% of the
upper-bound seconds across runs. That ratio is diagnostic because D019 and D030
are separate executions; the authoritative evidence is the within-D030 paired
13.892% saving.

## Decision

Do not extract, replay, or benchmark the C1 cohort. Do not request a cluster
allocation. The exact automatic certificate mechanism is useful on these
theorems but not promising enough to justify the planned 16,160-proposal run.
The earlier 1.84x sensitivity point assumed full retention of an upper bound and
is superseded as a planning estimate by this direct paired overlap evidence.

Any future successor needs a materially different mechanism with its own
compute-free argument. Merely narrowing the same cohort or quoting selected
fast certificate pairs does not reopen C1 execution.

## Reproduction

```bash
PYTHONPATH=src python -m lean_prefix.retention_gate
```

Authoritative aggregate: `reports/c0_rl_retention_gate.json`.
