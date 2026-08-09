# D017 diagnostic breadth hand review

Date: 2026-08-09

Selection: inspect the highest per-theorem opportunity, the highest absolute
baseline and tactic costs, an all-incorrect high-reuse theorem, and every
fallback class in the deterministic six-shard breadth run. Proposal IDs and
aggregate selection inputs are preserved in
`reports/c0_replay_breadth_d017.json`; raw proposal records remain private.

## Verdict and accounting strata

- All 14,496 complete-proof verdicts agree with C0.
- All 12,758 profile-eligible verdicts agree with the unchanged baseline.
- There are no full/profile request failures, timeouts, or missing CPU values.
- 1,508 native-eligible proposals use explicit profile fallback. The dominant
  reasons are top-level `<;>` (1,092), `induction'` (271), `Lean.cdot` (63),
  `Lean.calcTactic` (43), and smaller combinations of structural controls.
  Seven malformed fenced outputs also fall back. These remain in the baseline
  denominator and create no claimed savings.
- 415 proposals have invalid theorem roots, accounting for 640 syntactic units
  that Lean cannot reach. Their complete negative verdict and baseline cost are
  retained; their tactic opportunity is zero.

## High-reuse theorem

`lean_workbook_plus_67496` proves the cosine sum identity. Its measured
opportunity is 44.53% (2.93 of 6.59 baseline CPU seconds). Hand inspection
confirms genuine exact repetition rather than a parser artifact:

- candidates 0, 1, 7, 15, and 26 share the exact `rw; simp; ring` path;
- eight correct candidates share the exact `have; have; simp; linarith` path;
- the repeated `simp`, `ring`, and `linarith` work is nontrivial and receives
  the same prefix hash only when all preceding source slices are exact;
- unique alternatives (`field_simp`, `refine`, `simp_all`) remain unique.

This is the behavior the proposed executor is designed to exploit.

## Expensive but mostly unique theorem

`lean_workbook_plus_64419` is the largest complete request in the breadth set.
Candidate 31 is Lean-correct and consumes 33.98 CPU seconds, of which 32.57 are
attributed to its third `simp`. That expensive prefix occurs only once. Several
other candidates share cheap first and second prefixes, but exact divergence
before the extreme `simp` prevents the engine from claiming its cost. This is
the clearest hand-checked reason that 22.43% syntactic reuse does not translate
to a comparable CPU opportunity.

## Shared failures with useful work

All but one attempt for `lean_workbook_plus_61820` are incorrect. Fifteen begin
with the same `rw [hn, ho, hp]`, and six share the subsequent `field_simp`;
their repeated failed-path computation is still genuine work that an exact
executor could avoid. The theorem's opportunity is 29.38% (4.87 of 16.59 CPU
seconds). The sole correct proposal diverges to unique `subst_vars`,
`field_simp`, and `nlinarith`, so it is not incorrectly credited with the
failed candidates' work.

## Expensive incorrect outlier

Proposal
`3a258dd5e89f697a253f379f3b74dea0d0ee634025810704b2cad13988140c10`
for `lean_workbook_plus_30281` is incorrect and consumes 15.67 CPU seconds.
About 7.99 seconds are attributed to its second `have ... := by aesop`; that
exact rooted prefix is unique. It contributes to the full baseline denominator
but no reusable-prefix savings. This confirms that the accounting does not
reward a costly tactic merely because its tactic head resembles other `have`
steps.

## Interpretation

The diagnostic breadth estimate is 6.463% of independent-verification CPU, with a
theorem-bootstrap interval of 5.519%–7.501%. The six shards were selected as a
deterministic semantic/operational breadth set, not as the registered complete
sample, so this does not decide the frozen 15% gate. It is nevertheless an
important warning: expensive outliers are often downstream of unique prefixes,
while high reuse tends to occur in moderate-cost proof families. The complete
census should proceed unchanged; neither equality nor the threshold should be
relaxed in response. D017 predates the final ambiguity-safe duplicate-frame
matcher, which can only remove claimed opportunity. Its verdict and qualitative
hand-review evidence remain valid, but its numeric cost estimate is not the
final-code breadth result.
