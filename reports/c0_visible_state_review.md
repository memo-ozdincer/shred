# D021 visible-state reconvergence hand review

Date: 2026-08-09

Authority: `reports/c0_visible_state_summary.json` and the raw D021 artifacts
whose hashes it records. This review is diagnostic-only. An exact printed goal
is not a complete Lean-state identity or an executable cache key.

## Reproducible aggregate

**Measured.** The frozen top-ten selection contains 320 proposals. D021 aligns
190 and sends 130 to explicit fallback, including two timeouts and six
deterministic `allTactics` process exits. All 312 requests with available
current verdicts agree with D019.

**Measured.** Exact theorem, printed goal, and exact tactic grouping has a
15.419% selected-CPU opportunity upper bound. The same records have 5.408%
exact-prefix opportunity, leaving a 10.011-point visible-state increment. The
selection was constructed to maximize an unsafe edge opportunity and is not a
corpus-wide estimate.

**Measured.** The accepted closing-tactic subset has a 13.760% upper bound and
an 8.617-point increment beyond exact prefixes. Two `rfl` groups supply 6.132
of those points. Excluding `rfl`, the closing increment is 2.485% of selected
full-verification CPU.

## Cases read by hand

### Expensive `rfl` after different normalizations

**Observed.** In theorem `lean_workbook_plus_41132`, candidates 12, 21, and 29
reach the identical printed goal before `rfl` after these distinct first steps:

```text
rw [Finset.sum_eq_multiset_sum]
simp only [Finset.sum, Finset.mem_range]
simp only [Finset.sum_eq_multiset_sum, Finset.mem_range]
```

Their attributed `rfl` costs are 137.699, 133.237, and 108.877 CPU seconds. The
group contributes a 253.208-second visible-state increment beyond prefixes.

**Observed.** Candidates 9 and 10 of the same theorem reach another identical
goal before `rfl` after `norm_num [Nat.choose_eq_factorial_div_factorial]` and
`norm_num at *`. Their attributed costs are 132.198 and 128.184 seconds, for a
130.191-second increment.

**Hypothesis.** These costs may be dominated by definitional equality and
kernel reduction rather than tactic search. Reusing an `Eq.refl` proof can
therefore leave most of the cost intact. They are a reason to measure cached
certificate application, not evidence that it will be fast.

### Redundant preambles converge before `positivity`

**Observed.** In theorem `lean_workbook_plus_24316`, candidates 2, 10, and 24
reach the same printed goal and exact `positivity` call after visibly different
histories:

```text
simp; norm_num; apply; ring_nf; field_simp; ring_nf; positivity
apply; ring_nf; field_simp; ring_nf; positivity
simp; ring_nf; norm_num; apply; field_simp; ring_nf; positivity
```

The attributed closing costs are 31.771, 32.236, and 31.392 seconds. This group
contributes a 63.599-second increment beyond exact prefixes.

**Observed.** This is genuine model-rollout behavior rather than tactic-head
similarity: different syntactic preambles normalize away before the same
downstream obligation. The exact tactic text, theorem, and printed goal all
match.

### Different paths converge before `ring_nf`

**Observed.** Candidates 1, 14, and 19 of theorem 24316 reach the same exact
`ring_nf` edge after paths that differ by `simp`, `norm_cast`, and earlier
normalization. Their attributed costs are 22.561, 24.072, and 23.862 seconds,
for a 46.997-second increment.

**Caveat.** This `ring_nf` is not a closing tactic in all members. Reusing an
arbitrary state transformation requires substantially more proof-state and
proof-term machinery than reusing a closing certificate. It remains out of
scope for the next gate.

### Different normalization scopes converge before `nlinarith`

**Observed.** In theorem `lean_workbook_plus_81687`, candidates 0 and 15 use
`ring_nf at hab` and `ring_nf at *`, respectively, then reach the same printed
goal before the exact closing call
`nlinarith [ha, hb, hc, hd, he, hf, hab]`. Its attributed costs are 24.501 and
24.409 seconds, for a 24.455-second increment.

### Negative control for the decomposition

**Observed.** Closing `norm_num` contributes 122.351 seconds of apparent reuse,
but all of it is already accounted for by exact prefixes; its incremental
visible-state contribution is zero. This confirms that the report does not
rename ordinary prefix duplication as reconvergence.

## Instrumentation failures

**Measured.** The 48 GiB D021 capture and independent 120 GiB D022 retry both
fail on the same four candidates of theorem 80508. Increasing the memory cap
does not change the result. D022 is excluded from the aggregate, and all six
D021 process exits plus both timeouts contribute zero opportunity.

## Decision

**Decision.** The evidence supports one bounded successor test, not a general
state-DAG project. Extract or otherwise reproduce closing proof certificates
for the hand-audited groups, apply them only to exactly matched goals and local
contexts, and measure the complete ordinary-Lean elaboration and kernel-check
cost against regenerating the original tactic. Unsupported contexts fail back
to independent execution. Full-state identity, non-closing transition reuse,
and kernel-level memoization remain deferred until that test passes.
