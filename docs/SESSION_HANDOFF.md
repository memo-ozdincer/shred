# Session Handoff

Last updated: 2026-08-09 Eastern

This is the authoritative operational handoff for Lean Prefix (working project
name: Shred). The repository is `/scratch/memoozd/rl/lean-prefix`; the private
remote is `memo-ozdincer/lean-prefix`, branch `main`.

## Claim and boundary

The only proposed intervention is:

```text
independent execution of complete Lean proof attempts
    -> exact shared-prefix-trie execution of those same attempts
```

Proofs, theorem statements, Lean/Mathlib, timeouts, final acceptance, and every
proposal's attribution remain unchanged. Version one shares only exact rooted
top-level tactic prefixes for attempts at the same theorem. Unsupported syntax
uses explicit independent fallback. There is no semantic state merging, tactic
similarity, proof invention, search change, or GPU component.

## Frozen inputs

- C0: 9,655 theorems, 308,960 registered proposals, 168,029 Lean-correct;
- 32 padding records are separately accounted for and excluded;
- corpus: `data/c0/proofs/part-0001.jsonl.gz` through `part-0004.jsonl.gz`;
- manifest: `data/c0.manifest.json`;
- native units: `artifacts/c0_native_units.jsonl.gz`;
- native artifact SHA-256:
  `c53e4240355373d1b16c80634305f1b3611f6970607267479a3825ac8e3d4331`;
- Mathlib workspace: `/scratch/memoozd/rl/DeepSeek-Prover-V1.5/mathlib4`;
- Mathlib commit: `2f65ba7f1a9144b20c8e7358513548e317d26de1`;
- toolchain: `leanprover/lean4:v4.9.0-rc1`;
- REPL commit: `c6199a81de2a7e16cb27d6f85f56cff7043cd27f`;
- reproducibly patched REPL:
  `artifacts/repl-patched-c6199a8-v2/.lake/build/bin/repl`;
- patched executable SHA-256:
  `89a35afd9f7a472b45e57dfd5dd0cede08bd0485ca4ac71b860d486cde8a42f3`.

The Mathlib workspace has a pre-existing modified `lake-manifest.json`. Every
run records that dirty state; do not silently clean or update it.

## Evidence so far

Phase 1 measured 42,815 exact duplicate occurrences, 304,546 parseable
proposals, 888,421 eligible tactic occurrences, 689,193 exact trie nodes, and
199,228 syntactically reusable occurrences. This is opportunity by count, not
by cost.

The first complete Phase 2 diagnostic covered all 308,960 proposals but is not
valid cost evidence. Under 112-way execution it had 36 C0 parsing mismatches,
72 reconstructed-replay mismatches, 35 process errors, 118 complete-request
timeouts, and 6 replay timeouts. D-012 fixes exact fenced parsing; D-013 rejects
reconstructed proof states because hidden Lean elaborator/recursion context can
change both verdict and cost.

D-014 is the corrected method. An unchanged complete request supplies the
authoritative verdict and process CPU. A separate identical declaration with
Lean's C profiler enabled supplies exclusive tactic frames. Frozen native units
are aligned deterministically, and only a conservative share of baseline CPU
is attributable to exact prefixes. Profiler overhead is reported separately.
No tactic is wrapped, repaired, or submitted standalone for this measurement.

The mismatch-family regression at
`artifacts/replay_targeted_d016_profiler_v3.jsonl.gz` completed in 26.8 seconds:
19/19 unchanged full-verdict agreement, 14/14 profile-eligible verdict
agreement, 5 structural fallbacks, 32 reached units, and no errors/timeouts.
Artifact SHA-256:
`29584e3207cf9f97875f933e6d48f041dcb3a4b9800a7d32edb94628e7a75f1c`.
This validates the correction but is intentionally not a performance sample.

## Live allocation

- Slurm allocation: `19352896`;
- node: `c126.nibi.sharcnet`;
- resources: 192 CPUs and `766000M` RAM;
- scheduled end: 2026-08-09 16:00:53 Eastern;
- allocation state: running; do not cancel it;
- D019 step `19352896.76`: completed in 3:06:50;
- allocation remains running and must not be cancelled.

Step `19352896.63` completed the six-worker D017 breadth gate in 20.2
minutes. All 14,496 full verdicts and all 12,758 profile-eligible verdicts
agree, with 1,508 explicit fallbacks, 32,054 profiled units, zero errors or
timeouts, and no missing CPU. The aggregate is
`reports/c0_replay_breadth_d017.json` (SHA-256
`19c05a910533d48523dfd109fd79e0b9b2819444d0494b539e640bd1511bf59d`).
The hand review is `reports/c0_replay_breadth_d017_review.md`.

Its diagnostic CPU opportunity is 6.463% and its theorem-bootstrap interval
is 5.519%–7.501%. This is below the frozen 15%, but D017 is an operational
breadth set rather than the registered complete sample. It also started before
the final fail-closed rule for ambiguous duplicate profiler frames was added.
That rule cannot increase opportunity, but it changes eligibility, so D017's
cost estimate is diagnostic and must not be represented as final-code output.

## Complete D019 result

D019 has 128 reports, 128 gzip artifacts, and exactly 308,960 proposals. It
contains 168,032 current acceptances, 140,784 rejections, 124 timeouts, 20
process deaths, three historical C0-label disagreements, and zero
profiler-induced disagreements. The strict summarizer refuses a claim. The
checked-in diagnostic decomposition is
`reports/c0_opportunity_decomposition.json`, SHA-256
`92ef7b7e2edf3a2e6452d549596ee1624f958e8331f9dc172f96e96614009e64`.
Its exact-prefix estimate is 3.762% (bootstrap 3.401%–4.159%), so D-017 stops
the version-one executor.

## Exact next actions

1. Run the frozen D026 automatic prevalence selection and paired measurement:
   128 deterministic representative theorems plus 32 separately labeled
   enriched theorems.
2. Consolidate only complete theorem artifact/report pairs and require exact
   paired verdict accounting.
3. Hand-audit automatic hits and misses, including local-context permutations,
   typeclass state, and large-certificate fallback behavior.
4. Apply D-023's gate before building a production cache: zero representative
   verdict disagreements and at least 15% representative end-to-end CPU saving.

The implementation is `lean/LeanPrefix/AutomaticCertificate.lean`; its Lean
exercise is `lean/LeanPrefix/AutomaticCertificateTest.lean`. Selection,
read-only input preparation, paired theorem execution, and strict consolidation
are in `src/lean_prefix/certificate_prevalence.py` and exposed through the CLI.

D026 step `19352896.105` is invalid and was cancelled without cancelling the
allocation. The module was imported but its tactic namespace was not opened,
so cached proofs failed as unknown tactics. D-024 quarantines all D026 raw
outputs. The context now explicitly opens `LeanPrefix.AutomaticCertificate`;
the corrected run must use `certificate_d027` and must not consolidate D026.

D027 step `19352896.111` is also quarantined. A partial audit found 36
correct-to-incorrect disagreements because a main-goal certificate was applied
where the original final tactic closed sibling goals too. D-025 now requires
exactly one outstanding goal; multi-goal states are uncacheable fallbacks. The
next clean run name is `certificate_d028`; never consolidate D026 or D027 with
it.

D020 was stopped after eight theorem reports. Persistent `allTactics`
`ProofSnapshot` data caused cumulative memory growth (roughly 45 GiB in one
worker under a 48 GiB cap), and theorem 80508 recorded four process errors.
D-019 therefore requires a fresh REPL process per proposal. D021 subsequently
completed all 320 frozen proposals in step `19352896.91`: 190 aligned, 130
fallback, two timeouts, six process exits, and 312/312 current-verdict agreement
with D019. D022 retried theorem 80508 at 120 GiB and reproduced the same four
process exits, so they are deterministic instrumentation failures rather than
memory-cap failures. D022 is excluded from the aggregate. Allocation `19352896`
on c126 remains running and must not be cancelled.

The authoritative D021 aggregate is
`reports/c0_visible_state_summary.json`, SHA-256
`2358fb685a77ed65c9058e341fdd65695719f12399ccbaa0371c0ea624c4fbdb`.
It records clean summary commit `610befa` and clean capture commit `9ddac5f`.
The hand audit is `reports/c0_visible_state_review.md`.

D024 step `19352896.103` ran for 312.947 wall seconds. Ordinary Lean accepted
the transferred `nlinarith` and `positivity` certificates at 325.6x and 27.1x
generation-plus-check to application-plus-check. The raw `eqRefl` target failed
unchanged default `maxRecDepth`, so the step correctly exited nonzero and that
pair is not a hit. The raw logs are under
`reports/private/certificate_d024/`; D023 is a preserved launcher failure from
unavailable `/usr/bin/time`. D025 step `19352896.104` is the clean registered
two-pair rerun from commit `7424ace`; it completed with exit code zero in
128.511 wall seconds. The tracked aggregate is
`reports/c0_certificate_probe.json`, SHA-256
`4a77f798236c236f874aa4e237f77c2ead835ba6d31445380d6cdc85ced72fa1`.
Its ignored raw stderr profile is
`reports/private/certificate_d025/stderr.log`, SHA-256
`3342feac1cc3164fce80534ffd6503c61c8def3b332e3991ee5b74762fc465b9`;
stdout is empty. D025 measures 325.2x for `nlinarith` and 27.1x for
`positivity`, generation-plus-check to application-plus-check.

Raw proposal-level traces and the native artifact are Git-ignored and live on
`/scratch`; aggregate reports and documentation belong in Git. A shard is
complete only when both its gzip artifact and JSON report exist. A partial gzip
without a report may be safely overwritten with the same deterministic shard
command.

The interrupted `replay_d018_breadth` attempt is diagnostic only. It discovered
that no-alignment valid roots were conservatively zero-cost but mislabeled as
eligible/unreachable. D-016 fixes this, and a five-proposal regression verifies
four explicit fallbacks plus one distinct invalid root. Do not consolidate or
resume that directory; use `replay_d018_breadth_v2`.

The clean `replay_d018_breadth_v2` rerun is complete and passes: 14,496/14,496
full verdicts and 11,841/11,841 profile-eligible verdicts agree; 2,425 fallbacks
are explicit; 29,011 units are profiled; and there are no errors, timeouts,
missing CPU values, or missing/duplicate proposals. The conservative breadth
estimate is 5.911% (bootstrap interval 4.964%–6.959%). Its report is
`reports/c0_replay_breadth_d018.json`, SHA-256
`ae242d29aedf989d0277ec6dde30d6b6869d1004086d43bb911fc8108f3cc628`.
It is retained as the clean operational precursor to the now-complete D019
census.
