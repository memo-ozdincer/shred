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

## D-003 — Use the C0 Lean/Mathlib environment as the syntax authority

Date: 2026-08-08

Status: accepted

Decision: parse tactic sequences with Lean `v4.9.0-rc1` and Mathlib commit
`2f65ba7f1a9144b20c8e7358513548e317d26de1`, matching the C0 verifier
workspace. Prefix identity is the exact UTF-8 source slice from the previous
tactic boundary through the current Lean-native tactic boundary.

Reason: a line splitter or current Mathlib parser can manufacture or erase
boundaries. Retaining comments and whitespace makes version-one equality
strict, deterministic, and auditable.

Consequence: formatting-equivalent prefixes are intentionally not shared.
Normalization is deferred until it can be proved semantics-preserving.

## D-004 — Conservative fallback for unsafe or unsupported roots

Date: 2026-08-08

Status: accepted

Decision: malformed outputs, unknown tactics, bracketed root sequences, and
top-level semicolon sequences are ineligible for prefix execution and must use
the independent verifier.

Reason: `t₁; t₂` applies `t₂` to every goal created by `t₁`; treating it as two
ordinary sequential edges would be wrong. Bracketed roots also require explicit
scope semantics. An explicit fallback preserves verdicts while the minimal
engine remains small.

Consequence: 4,414 C0 proposals (1.43%) fall back under this rule, including
some Lean-correct proposals. They remain in workload and compute accounting.

## D-005 — Pre-registered cost-opportunity gate

Date: 2026-08-08

Status: accepted before cost-weighted replay

Decision: proceed from replay telemetry to the shared executor only if repeated
exact, actually reached prefixes account for at least 15% of independent
verification CPU time on C0. Also report a theorem-bootstrap 95% interval and
the full per-theorem distribution; do not substitute the global mean for the
threshold.

Reason: removing 22.43% of syntactic tactic occurrences is promising but does
not establish useful savings. Tactics vary greatly in cost, and incorrect
proofs can fail before later parsed units execute.

Consequence: if the gate fails, publish the characterization and stop the
version-one engine rather than broadening equality after seeing the result.

## D-006 — Replay reached root tactics from pinned REPL snapshots

Date: 2026-08-08

Status: accepted

Decision: Phase 2 first checks each original complete proof through the same C0
imports and options. Independently, it creates one immutable theorem-root proof
state with a temporary `sorry`, branches every proposal from that root, and
executes its exact native units sequentially until completion or the first
failure. Each reached unit records process CPU, wall time, peak RSS, result, and
Lean heartbeats. Both the complete-proof verdict and sequential replay verdict
must agree before costs are used.

Reason: syntactically present tails after a failed tactic consume no verifier
work. Root-state replay observes actual reachability, handles structural syntax
such as bullets without relying on filtered info-tree ranges, and directly
exercises the state-branching primitive required by the proposed executor.

Consequence: units after the first failed or timed-out unit are labeled
`unreachable_after_failure`. A complete-proof/sequential disagreement, missing
root snapshot, timeout, or missing replay blocks the gate.

## D-007 — Keep the upstream REPL protocol unchanged

Date: 2026-08-08

Status: accepted

Decision: communicate with the pinned REPL commit
`c6199a81de2a7e16cb27d6f85f56cff7043cd27f` through a private pseudo-terminal.
Disable echo and canonical input, retain the upstream JSON protocol, and apply
timeouts and a 24 GiB address-space limit from the parent process.

Reason: the upstream process buffers ordinary-pipe responses and canonical
terminals truncate sufficiently long one-line JSON. PTY transport with those
flags fixes both transport properties without forking Lean or the verifier.

Consequence: Linux PTY and `/proc` process CPU/RSS telemetry are explicit Phase
2 platform requirements. Heartbeats remain available as Lean-native effort
telemetry when OS CPU clock granularity is too coarse for cheap tactics.

The requirement that the REPL executable itself remain byte-for-byte upstream
is superseded by D-010 after authentic replay showed that upstream proof
snapshots omit context required to preserve the C0 execution policy.

## D-008 — Use measured occupancy on standard-memory CPU nodes

Date: 2026-08-08

Status: accepted for the Phase 2 run

Decision: run 128 deterministic shards with at most 112 concurrent workers on
a 192-core Nibi node with `766000M` allocated memory. Retain the 24 GiB
per-process address-space limit and restart each REPL after 128 proposals.

Reason: the hard address-space limit is a safety ceiling rather than reserved
physical memory. Integration profiling observed at most 3.71 GiB RSS per REPL;
112 workers therefore leave substantial node headroom at the observed peak.
Waiting for one of ten 6 TiB nodes would add scheduling delay without evidence
that the workload needs that capacity.

Consequence: inspect aggregate memory after 30 and 60 minutes and reduce
concurrency if available memory falls below 100 GiB or the scheduler reports
memory pressure. This operational decision changes parallelism only, not the
proof workload, verifier, timeouts, or scientific gate.

## D-009 — Invalid theorem roots have zero reached tactic work

Date: 2026-08-08

Status: accepted after the first full-corpus launch exposed malformed C0
theorem declarations

Decision: when root elaboration returns explicit Lean errors before producing a
proof state, record the proposal as `unreachable_invalid_root`, require its
sequential rejection to agree with the complete-proof verdict, retain its full
verification CPU time in the gate denominator, and assign zero reached tactic
work. An absent or malformed root snapshot without explicit Lean errors remains
a fatal profiler error.

Reason: C0 contains theorem strings that Lean cannot elaborate independently
of any proposed proof, including declarations with undeclared variables or
malformed binders. No tactic in those proposals can execute. Treating this as
missing telemetry aborts an authentic workload; treating the parsed tactics as
reached invents computation that Lean never performed.

Consequence: invalid-root proposals and their syntactic units remain explicitly
counted, conservatively reduce the measured opportunity fraction through the
full-verification denominator, and cannot create cache savings. The rule does
not make an invalid proof pass and does not exclude any proposal.

## D-010 — Patch only the proof-snapshot execution adapter

Date: 2026-08-08

Status: accepted before restarting the full Phase 2 run

Decision: build a reproducible three-hunk patch over pinned REPL commit
`c6199a81de2a7e16cb27d6f85f56cff7043cd27f`. The patch carries the theorem
declaration name in proof snapshots and restores C0's
`set_option maxHeartbeats 0` for each proof-step request. It does not modify
Lean, Mathlib, the kernel, the complete-proof verifier, any proof text, or the
final acceptance predicate. `Lean.cdot` and `Lean.calcTactic` units, which are
structural syntax rather than standalone tactics, use explicit independent
verification fallback. Any error-severity proof-step message is a failed step.

Reason: 14,496 completed authentic proposals had perfect complete-proof
agreement with C0 but 724 sequential disagreements. Hand inspection and raw
protocol reproduction identified four distinct causes: error messages were not
treated as failures; structural syntax cannot be submitted standalone; proof
snapshots dropped the declaration context needed for auxiliary declarations;
and proof-step execution silently reverted to 200,000 heartbeats despite C0's
unlimited setting. The last case included a valid tactic requiring more than
241 million heartbeats.

Consequence: `patches/repl-proof-snapshot.patch` and
`scripts/build_patched_repl.sh` are part of the measured execution adapter.
Every replay report records the resulting executable SHA-256. A six-proposal
regression set now has 6/6 complete-verdict agreement, 4/4 sequential agreement
for replay-eligible proposals, and two explicit structural fallbacks. The six
previously completed shards must be rerun before the full measurement resumes;
their earlier telemetry is diagnostic only.

## D-011 — Root errors dominate snapshots; unsafe telemetry is omitted

Date: 2026-08-08

Status: accepted after the corrected six-shard breadth rerun

Decision: if theorem-root elaboration returns any error-severity message, the
root is invalid even if the REPL also exposes a `sorry` snapshot. Separately,
execute `Lean.Parser.Tactic.«tactic_<;>_»` units verbatim without the optional
`count_heartbeats` wrapper; retain their process CPU, wall, RSS, and verdict
telemetry, and count their missing heartbeat measurements explicitly.

Reason: the corrected breadth rerun reduced 724 sequential disagreements to
98 while preserving 14,496/14,496 full C0 verdicts. Raw reproduction showed
that 96 arose from malformed declarations returning both an error and a
snapshot; selecting the snapshot manufactured a valid-looking goal containing
`sorryAx`. The remaining two valid `<;>` proofs succeed verbatim, while the
heartbeat wrapper alone triggers Lean's `invalid 'let_mvar%', metavariable ...
has already been used` error. Heartbeats are supplemental telemetry and may not
change tactic execution.

Consequence: error precedence is fail-closed and assigns zero reached work to
these invalid roots under D-009. The two `<;>` cases retain the primary OS cost
telemetry but have `heartbeats: null`; aggregate reports count
`heartbeat_uninstrumented_units`. The six-shard breadth gate must pass again
before a full-corpus launch.
