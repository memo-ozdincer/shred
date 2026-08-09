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

Status: superseded by D-013 for Phase 2 cost measurement

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

Status: superseded by D-015 after full-census contention was measured

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
before a full-corpus launch. It subsequently passed with zero full or sequential
disagreements across 14,496 proposals and no missing CPU telemetry.

## D-012 — Preserve C0 fenced parsing and stop at proof completion

Date: 2026-08-08

Status: accepted after the complete diagnostic census

Decision: mirror the C0 verifier's exact fenced-code regular expression before
submitting a full proof. A generated response without a matching closing fence
is an explicit independent-verification fallback and is never replayed as if
the missing delimiter had been repaired. During sequential replay, the first
error-free zero-goal response completes the proof even if no further proof-state
ID is returned. Later native units are recorded as
`unreachable_after_completion` and consume no replay cost.

Reason: the clean 128-shard diagnostic census covered all 308,960 proposals and
found 36 full C0-label disagreements, all C0-false to profiler-true. Inspection
showed that the profiler had stripped or forgiven missing closing fences while
C0 submitted `failed to parse`. The same census found valid proofs whose goals
closed before syntactically present trailing tactics; attempting those tails
manufactured sequential failures.

Consequence: fenced parse failures retain their independent baseline cost and
proposal accounting but cannot create prefix savings. Early-completion tails
are separately counted and excluded from reached-prefix cost. This correction
does not alter proof text, Lean, Mathlib, or the acceptance rule.

## D-013 — Reject reconstructed proof-state replay as cost evidence

Date: 2026-08-09

Status: accepted after targeted and full-corpus diagnostics

Decision: do not use tactics restarted from serialized or reconstructed proof
states to estimate the Phase 2 opportunity. Keep the patched REPL build as a
reproducible diagnostic and possible Phase 3 implementation dependency, but do
not treat its step-by-step replay timings as measurements of the unchanged C0
execution.

Reason: the diagnostic 128-shard census completed all 308,960 proposals, but
reported 72 sequential-verdict disagreements, 35 process errors, 118 complete
request timeouts, and 6 step-replay timeouts under 112-way concurrency. Exact
targeted replay showed the deeper problem: a complete proof may hit
`maxRecDepth` or fail inside nested simplification while the same visible goal
and tactic succeeds after a standalone proof-state restart. Chaining authentic
pre-tactic snapshots removed several discrepancies but not all of them because
the visible goal does not capture every elaborator and recursion context.

Consequence: these diagnostic artifacts cannot support a cost or verdict claim.
Phase 2 must measure tactics during an unchanged complete declaration. Phase 3
still requires its own exact verdict-equivalence tests; Phase 2 telemetry is not
permission to assume that arbitrary state reconstruction is equivalent.

## D-014 — Use Lean's in-process C profiler as a conservative cost oracle

Date: 2026-08-09

Status: accepted for the corrected Phase 2 measurement

Decision: for each eligible proposal, first run the unchanged complete proof as
the authoritative baseline and verdict. Then run the same declaration in the
same pinned environment with only `profiler` enabled and parse Lean's exclusive
`tactic execution of <syntaxKind>` records from that request's stderr. Match a
deterministic reached top-level prefix against the already frozen Lean-native
unit sequence. If syntax-kind-only profiler frames admit multiple ordered
alignments, fall back rather than selecting one. Allocate baseline process CPU
to each uniquely matched unit in proportion to its attributable profiler time
divided by the greater of the profiling
request's wall time and the sum of all attributed tactic time. This guarantees
that attributed tactic CPU cannot exceed the unchanged baseline CPU even if
profiler records overlap or round upward.
Report profiling CPU and wall time separately and exclude that overhead from
the gate denominator and savings.

For the first tactic, count only its own exclusive profiler frame because work
before it includes theorem elaboration. For each later tactic, count profiler
records after the preceding matched top-level frame through the current frame.
This is deliberately a lower bound: unattributed parent, parsing, linting, and
post-proof work cannot create claimed prefix savings. A profile timeout,
protocol error, missing deterministic alignment, parse failure, or currently
unsupported structural-control form falls back explicitly to independent
verification and contributes zero opportunity.

Reason: this method does not wrap, resubmit, repair, or independently execute a
tactic. The authoritative verdict still comes from the unchanged complete
request, whose high-resolution process CPU is read from Linux `schedstat`. A
19-proposal regression chosen from every known mismatch family completed in
26.8 seconds with 19/19 unchanged full-verdict agreement, 14/14 agreement for
profile-eligible proposals, 5 explicit structural fallbacks, 32 attributed
reached units, and no timeout, process error, or profile-verdict change. Its
documented-REPL artifact is
`artifacts/replay_targeted_d016_profiler_v3.jsonl.gz`, SHA-256
`29584e3207cf9f97875f933e6d48f041dcb3a4b9800a7d32edb94628e7a75f1c`.

Consequence: the pre-registered 15% threshold is now evaluated against a
conservative attributable CPU opportunity, not against the cost of an altered
standalone replay. The targeted mismatch set validates semantics but is not a
representative performance sample. A deterministic six-shard breadth gate must
pass before the complete census is launched.

## D-015 — Use 32 workers and a 48 GiB safety ceiling for the final census

Date: 2026-08-09

Status: accepted after the corrected six-shard breadth gate

Decision: run the complete 128-shard census with 32 concurrent workers, a 48
GiB per-process address-space ceiling, the unchanged 300-second timeout, and a
128-proposal REPL restart interval. Write it to the new `replay_d018` run name;
do not overwrite the earlier diagnostic census.

Reason: the corrected six-worker breadth gate completed 14,496 proposals in
20.2 minutes with zero request error or timeout. Active Lean processes used
approximately 3.7–4.1 GiB RSS and the 755 GiB node retained about 736–737 GiB
available. In contrast, the earlier 112-worker census produced severe
CPU/cache contention, long tails, 118 full timeouts, and 35 process exits
despite safe memory. Six-worker throughput projects about 1.4 hours at 32-way
parallelism; allow 2–4 hours for shard variance and tails.

The D017 breadth report is complete: 14,496/14,496 full verdicts and
12,758/12,758 profile-eligible verdicts agree, with 1,508 explicit fallbacks,
32,054 profiled units, and no missing CPU. Its conservative opportunity is
6.463% (theorem-bootstrap 95% interval 5.519%–7.501%), below 15%. Because the
six shards are an operational breadth set rather than the registered complete
sample, this is a warning rather than the final gate decision. D017 started
before the final ambiguity-safe frame matcher was frozen, so its verdict and
throughput evidence remains valid but its cost estimate is diagnostic. Repeat
the same breadth set from the clean commit before launching the full census.

Consequence: D-008's 112-worker recommendation and 24 GiB limit are superseded.
The final breadth rerun and complete census start only from clean committed
implementations. The
15% threshold, proof workload, verifier, parser, and profiler method remain
unchanged.

## D-016 — Missing or ambiguous profile alignment is explicit fallback

Date: 2026-08-09

Status: accepted after the first clean ambiguity-safe breadth attempt

Decision: if the in-process profiler has no unique ordered alignment to a
nonempty frozen tactic sequence and the theorem root itself is valid, mark the
entire proposal as an explicit independent-verification fallback. Do not label
its syntactic units `unreachable_after_completion` or
`unreachable_after_failure`. Invalid theorem roots remain separately classified
under D-009.

Reason: the first clean ambiguity-safe breadth attempt correctly assigned zero
cost to ambiguous profiler frames, but the root-validity probe then supplied a
proof-state ID that was accidentally treated as evidence of a successful
profile alignment. This could not inflate savings or alter a verdict, but it
misstated eligibility and reachability. A five-proposal regression containing
four known ambiguous valid roots and one invalid root now reports 4 explicit
fallbacks, 1 invalid-root proposal, 0 profiled units, 5/5 complete-verdict
agreement, and no error or timeout. Its artifact is
`artifacts/replay_targeted_d018_alignment_fix.jsonl.gz`, SHA-256
`63660e8d81f6832255de3db607712b684279e0bb5d4f6924cf1b8b06c646065c`.

Consequence: the interrupted `replay_d018_breadth` directory is diagnostic and
must not be consolidated. Repeat the same six shards as
`replay_d018_breadth_v2` from the clean fix commit before D019.

The clean D018-v2 rerun subsequently completed all 14,496 proposals with
14,496/14,496 full-verdict agreement, 11,841/11,841 profile-eligible verdict
agreement, 2,425 explicit fallbacks, 29,011 profiled units, and no error,
timeout, missing CPU, duplicate, or missing proposal. Its conservative
opportunity is 5.911% with a theorem-bootstrap 95% interval of
4.964%–6.959%. The report is `reports/c0_replay_breadth_d018.json`, SHA-256
`ae242d29aedf989d0277ec6dde30d6b6869d1004086d43bb911fc8108f3cc628`.
This passes the semantic and accounting gate for D019; it remains an
operational breadth set and therefore does not replace the registered complete
gate decision.

## D-017 — Stop the version-one executor after the complete census

Date: 2026-08-09

Status: accepted; primary gate failed

Decision: do not build the exact rooted-prefix executor. Preserve D019 and its
diagnostic decomposition, explicitly report the invalidating records, and stop
the version-one path rather than lowering the frozen 15% threshold.

Reason: D019 completed all 128 shards and all 308,960 proposals in 3:06:50.
The profiler-enabled copies caused zero verdict disagreement, but the ordinary
baseline found three historical C0-false labels that Lean now accepts and 20
process deaths without CPU telemetry. The registered summarizer therefore
correctly refused a performance claim. Even the diagnostic calculation, whose
missing failure cost can only inflate the fraction, estimates only 3.762%
exact-prefix opportunity (theorem-bootstrap interval 3.401%–4.159%). This is
far below 15%. There were also 124 accounted timeouts and 50,774 explicit
fallback proposals.

Consequence: `reports/c0_opportunity_decomposition.json` is diagnostic, not a
successful primary result. Phase 3 does not start. The failed gate and raw D019
artifacts remain reproducible evidence rather than being repaired into a more
favorable comparison.

## D-018 — Test state convergence only as a post-gate diagnostic

Date: 2026-08-09

Status: accepted for a bounded top-ten census

Decision: after preserving D-017, test one possible successor hypothesis:
different exact prefixes may reconverge to the same visible pre-tactic goal.
Select the ten theorems with the largest exact-edge-within-theorem cost upper
bound, capture authentic `allTactics` metadata during unchanged full
elaboration, and group only identical theorem, visible goal, and exact tactic.
This is deliberately selected for sensitivity and is not representative.

Reason: exact completed-proof memoization saves only 6.041% under a
worst-observed representative. Ignoring state and grouping the same exact
tactic edge anywhere within a theorem gives an 18.385%–20.685% upper bound,
while tactic-kind grouping gives 29.638%–34.938%. Those broader numbers are not
executable: tactic behavior depends on full Lean state, and D-013 already
proved that a pretty goal omits consequential hidden context. Authentic visible
goals are the cheapest stricter filter before attempting full internal-state
identity.

Consequence: a visible-goal match remains an unsafe upper bound and cannot
justify caching or a speed claim. Only a large retained opportunity would
justify designing a full-state fingerprint. A small retained opportunity ends
the semantic-state direction without a larger rerun. This diagnostic does not
retroactively alter the original repository claim or gate.

## D-019 — Isolate every `allTactics` capture process

Date: 2026-08-09

Status: accepted after interrupted D020

Decision: start a fresh Lean REPL process and recreate the unchanged C0 base
environment before every selected proposal. Preserve the partial D020 outputs
as diagnostic evidence, but never merge them into the registered aggregate.
Only the isolated D021 rerun is eligible for the visible-state census.

Reason: `allTactics` retains internal `ProofSnapshot` data in the REPL state.
During D020 that retained metadata accumulated across proposals: one worker
reached roughly 45 GiB RSS under its 48 GiB limit, another reached roughly
19 GiB, and theorem 80508 recorded four process errors. Those failures reflect
the diagnostic harness's lifetime, not a property of the frozen proposals.
Starting a new process does not alter the declaration or state metadata being
captured, and the census does not use initialization time as proof cost.

Consequence: every D021 report records `restart_every_proposals: 1`. The rerun
must preserve D019's current-verdict agreement and report all timeouts and
process failures explicitly. D020 remains diagnostic-only and cannot be
silently repaired, resumed, or consolidated with D021.

## D-020 — Preserve D021 as a bounded upper-bound diagnostic

Date: 2026-08-09

Status: accepted after complete D021 consolidation

Decision: preserve all ten D021 theorem captures, including their explicit
fallbacks, and report visible-state grouping only as a deliberately enriched
upper bound. Do not rerun or impute the unsupported records. The 120 GiB D022
retry of theorem 80508 is retained only as evidence about its failure mode and
is excluded from the aggregate.

Reason: D021 accounts for all 320 frozen proposals with 190 unique tactic
alignments, 130 fallbacks, two timeouts, and six process exits. The 312 requests
that returned current verdicts agree exactly with D019. Restarting for every
proposal removed cumulative memory growth, but the same four 80508 candidates
failed under both 48 GiB and 120 GiB limits. Those failures are therefore
deterministic `allTactics` instrumentation failures, not evidence that the
proposals need a larger memory cap.

Among the supported records, identical theorem, visible goal, and exact tactic
groups have a 15.419% CPU opportunity upper bound, versus 5.408% for exact
prefixes on the same selected records. The 10.011-point increment is not a
speedup: printed goals omit hidden state, and the ten theorems were selected
for maximal unsafe edge opportunity rather than representativeness.

Consequence: the bounded census supports hand-reading and one narrower
feasibility test, not a state-DAG implementation or general performance claim.
The six process exits and two timeouts contribute zero state opportunity.

## D-021 — Gate any successor on exact closing-certificate application

Date: 2026-08-09

Status: accepted as the next bounded question

Decision: before designing full-state identity or arbitrary state-transition
reuse, test whether an expensive closing tactic's generated proof can be
reapplied to an exactly matched goal and local context, then accepted by
ordinary Lean for less CPU than regenerating the tactic result. Restrict the
first test to hand-audited convergent groups and make every unsupported context
an explicit fallback.

Reason: 113 accepted, aligned proposals end in a measured closing tactic. Their
visible-state opportunity upper bound is 13.760% of selected full-verification
CPU, but 8.617 percentage points are beyond exact prefixes and 6.132 of those
points come from two `rfl` groups in theorem 41132. Applying a cached proof
still incurs elaboration, definitional equality, and kernel checking; the
large `rfl` cost may therefore survive certificate reuse. Excluding `rfl`, the
closing increment beyond prefixes is only 2.485% of selected CPU. An actual
application-cost measurement is necessary before calling this a project.

Consequence: no general semantic cache is in scope yet. A successor survives
only if ordinary Lean accepts the transplanted certificate and the measured
end-to-end saving remains material after kernel checking. The initial project
and failed exact-prefix gate remain unchanged.

## D-022 — Advance certificate reuse to a prevalence gate

Date: 2026-08-09

Status: accepted after authentic D024 feasibility probe

Decision: preserve the two passing manual-key closing-certificate pairs as
evidence that cross-proposal reuse can be semantically and computationally
feasible. Preserve the `rfl` pair as a fail-closed negative case. Advance only
the supported mechanism to automatic-key and prevalence measurement.

Reason: D024 tests three hand-audited D021 cases whose different tactic histories
reach the same printed goal: two valid transfers and one fail-closed negative
case. The source tactic's assigned proof is abstracted
over non-implementation-detail locals, instantiated in the target context,
checked for definitional type equality, assigned to the target goal, and then
checked by ordinary Lean as part of the target declaration.

The authentic profiler results are:

- theorem 81687: `nlinarith` generation plus source checking takes 24.107 s;
  certificate application plus target checking takes 0.0740 s (325.6x);
- theorem 24316: `positivity` generation plus source checking takes 20.024 s;
  application plus target checking takes 0.738 s (27.1x);
- theorem 41132: `eqRefl` generation takes 88.8 s and source checking takes
  95.7 s. The application tactic frame takes 9.1 ms, but the target declaration
  fails under Lean's unchanged default `maxRecDepth`. It is not a valid hit and
  no speedup is claimed.

The first probe failed on synthetic examples because hidden recursive
implementation-detail locals were abstracted into the certificate. Filtering
those locals fixed the test; target context-size and proof-type mismatches still
fail closed. This reproduces D-013's warning and is part of the evidence, not an
implementation detail to hide.

Lean's built-in incremental `checkpoint` cache is relevant prior art and an
architectural guide, but it keys a snapshot by the same metavariable identifier
and source position. D024 instead reuses a generalized proof expression across
different theorem elaborations reached by different tactic histories. The
distinction must remain explicit in any novelty claim.

Consequence: the next registered question is how often a safe automatic key
hits supported closing certificates outside the deliberately enriched top ten,
and how much end-to-end batch CPU it saves after keying, storage, checking,
misses, and fallbacks. Large raw proof expressions that exceed ordinary Lean's
limits remain fallback; a named auxiliary declaration is a separate future
design. Arbitrary non-closing state transitions remain out of scope.

## D-023 — Freeze the automatic closing-certificate prevalence contract

Date: 2026-08-09

Status: accepted before implementation

Decision: key a closing certificate by (1) a pinned Lean/Mathlib/base-context
fingerprint, (2) the exact structural syntax of the closing tactic with source
locations and trivia removed, and (3) the fully elaborated goal abstracted over
the ordered non-implementation-detail local context. Retain binder information.
Instantiate assigned metavariables and reject keys or certificates containing
unresolved metavariables, universe metavariables, or free variables. Hashes are
indexes only: every candidate hit must pass exact structural key equality,
local-count agreement, inferred-type checking, definitional equality with the
current target, and ordinary Lean checking of the completed declaration.

The tactic identity is part of the key because replacing a failing tactic with
a proof found by a different tactic would change the registered proposal's
verdict. A miss, unsupported context, rejected certificate, resource-limit
failure, or process reset executes the original tactic unchanged. Cache hits,
misses, captures, rejected captures, rejected applications, resets, time, and
verdicts must remain explicit.

Measure two frozen strata: a deterministic hash sample of 128 C0 theorems for
an unweighted prevalence diagnostic, and 32 non-overlapping theorems selected
by the largest repeated-final-edge D019 CPU opportunity for mechanism discovery.
The latter is enriched and cannot estimate corpus prevalence. For every chosen
theorem, compare a warm persistent REPL running the original proposals with a
separate persistent REPL running the wrapped closing tactics from the same base
environment and in the same proposal order. Preserve all 32 registered
proposals, including incorrect, unsupported, failed, and timed-out attempts.

Reason: pretty goals are not executable identities, and a goal-only cache can
change an incorrect proposal into a correct one. Exact tactic syntax plus the
abstracted elaborated context/target is the smallest auditable identity that
tests the supported D024 mechanism without introducing tactic invention or
state-DAG semantics. REPL requests all branch from the same initialized
environment while the module-level certificate store persists, permitting
cross-proposal reuse without allowing earlier candidate declarations to alter
later tactic search.

Consequence: this is a post-gate successor diagnostic, not a revival or
reinterpretation of the failed exact-prefix claim. No production cache is
authorized until the representative stratum has zero verdict disagreements,
automatic hits survive hand audit, and measured end-to-end savings remain
material after all overhead and fallback work.

## D-024 — Quarantine the invalid D026 namespace run

Date: 2026-08-09

Status: accepted during D026 execution

Decision: cancel only D026 step `19352896.105`, retain its raw outputs under
the D026 names for debugging, and exclude every D026 cached verdict and timing
from scientific consolidation. Preserve the allocation. Add the missing
`open LeanPrefix.AutomaticCertificate` to the pinned REPL context, require a
successful authentic wrapped smoke to emit cache events, and use a new D027
run directory for the corrected measurement.

Reason: a partial paired consolidation after 158 theorem reports showed 2,469
representative verdict disagreements, near-zero cached CPU, and zero cache
events. The module was imported, but its namespaced tactic syntax was not
opened in the generated REPL context, so instrumented proofs failed immediately
as unknown tactics. This is an instrumentation failure, not evidence about
certificate prevalence or speed.

Consequence: D026 is diagnostic-only and must never be merged with D027. The
failure demonstrates why partial verdict consolidation is mandatory during
long performance runs. The frozen theorem selection and prepared inputs remain
valid because neither depends on the faulty REPL context.
