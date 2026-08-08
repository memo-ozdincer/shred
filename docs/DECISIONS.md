# Decision Log

## D-001 — Exact rooted prefixes define version-one reuse

Date: 2026-08-08

Status: accepted

Decision: version one uses a rooted prefix trie over exact Lean-native tactic
units for candidates sharing the same pinned environment, context, and theorem.
It does not merge differently reached states or use approximate similarity.

Reason: this produces a deterministic, auditable intervention with a direct
ordinary-execution baseline and avoids making state-equivalence recognition a
second scientific mechanism.

Consequence: some reusable computation will be missed deliberately. Broader
state merging remains in `FUTURE.md`.

## D-002 — C0 is discovery data, not a final performance test

Date: 2026-08-08

Status: accepted

Decision: use the frozen C0 corpus to establish feasibility, parsing coverage,
and implementation requirements. Freeze implementation choices before the
primary held-out performance evaluation.

Reason: designing and evaluating entirely on the same 308,960 proposals would
overstate generality and invite workload-specific optimization.

