# Project Charter

## Problem

AI proof systems generate many complete attempts for the same Lean theorem.
Independent verification repeats theorem initialization and identical early
tactic execution, and batch barriers allow a slow attempt to delay completed
work.

## Primary hypothesis

Exact rooted tactic-prefix reuse reduces total verification work enough to
improve authentic rollout throughput while preserving every ordinary Lean
verdict and proposal-level accounting.

## Single intervention

```text
warm independent proof execution -> exact shared-prefix-trie execution
```

All other experimental factors remain fixed.

## Version-one input and output

Input:

- a pinned Lean project and environment;
- one theorem statement and context;
- an ordered collection of complete tactic-mode proof bodies;
- fixed timeout and resource settings.

Output:

- one ordinary Lean accept/reject/error/timeout result per original proposal;
- explicit execution, fallback, cache, and resource accounting;
- an auditable mapping from each proposal to the nodes it used.

## Success conditions

Correctness:

- zero acceptance disagreements against ordinary Lean on the registered corpus
  used for evaluation;
- deterministic proposal attribution;
- unsupported and effectful cases safely fall back;
- failures and timeouts remain failures or timeouts under the registered rule.

Systems value:

- material reduction in cost-weighted repeated work on the discovery corpus;
- material throughput or CPU-time improvement against a warm, equally
  provisioned independent baseline;
- no hidden proposal dropping and no unacceptable tail-latency or memory
  regression.

Scientific value:

- a reproducible characterization of prefix reuse in real model rollouts;
- a clear account of where reuse helps and where it does not;
- results on a workload not used to choose implementation thresholds.

## Non-goals

- improving proof success rate;
- choosing or generating tactics;
- semantic proof diversity;
- approximate textual matching;
- merging differently reached states;
- changing Lean's trusted kernel or acceptance semantics;
- optimizing an RL algorithm;
- creating a general cloud platform in version one.

