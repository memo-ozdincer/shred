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
- next run name: `replay_d018_breadth_v2`; final census name: `replay_d019`.

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

## Exact next actions

1. Commit and push the implementation, decisions, status, and aggregate report
   under `Memo Ozdincer <73766315+memo-ozdincer@users.noreply.github.com>`.
2. Rerun shards 7, 46, 53, 62, 78, and 93 as `replay_d018_breadth_v2`
   from that clean commit and require the same completeness/verdict conditions.
3. Commit its aggregate, then launch the full 128-shard `replay_d019` census
   with 32 workers from the resulting clean commit. Resume by missing report;
   never overwrite a completed report casually.
4. Monitor completed reports, aggregate/max RSS, available memory, errors,
   timeouts, and throughput at 30 and 60 minutes.
5. Consolidate exactly 308,960 proposal IDs. Only that representative result
   decides the frozen 15% gate.

If the complete gate passes, Phase 3 begins with a frozen warm independent
baseline, followed by the smallest exact prefix-trie executor and verdict,
attribution, isolation, fallback, timeout, and accounting tests. If it fails,
write the characterization and stop the version-one executor path. Do not tune
the threshold or weaken exactness after observing the result.

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
