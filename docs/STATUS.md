# Project Status

## Productization milestone

SHRED now exposes a public `shred` Python namespace and a single `shred
profile` workflow. The command preserves the existing conservative audit,
Lean-native extraction, replay, fallback, accounting, and summary semantics,
but packages them behind one bounded screening/full-workload interface. The
historical `lean_prefix` module and `lean-prefix` command remain compatibility
surfaces.

The profiler reports a screening result by default and refuses to turn a
sample into deployment evidence. Full-workload results apply the registered
cost-weighted gate and direct below-gate workloads toward bounded expensive
closing-tactic analysis rather than enabling broad certificate caching.

Last updated: 2026-09-01

## Established

- The private repository is self-contained: all four audited C0 corpus shards
  are checked in.
- The frozen corpus contains 9,655 theorems, 308,960 registered proposals,
  168,029 Lean-correct proposals, and 32 separately excluded padding records.
- Phase 1 measured 42,815 exact duplicate occurrences, 304,546 conservatively
  parseable proposals, 888,421 tactic occurrences, and 689,193 exact trie
  nodes. The 199,228 repeated occurrences are syntax evidence, not a speedup.
- The source manifest, proposal identities, hashes, native tactic boundaries,
  deterministic review sample, and 15% reached-prefix CPU gate are frozen.
- Complete-proof verification matches C0's exact fenced-code parsing and Lean
  remains the sole correctness authority.

## Phase 2 correction

The first full 128-shard diagnostic covered all 308,960 proposals but cannot
support a cost claim. It exposed 36 C0 parsing mismatches, 72 reconstructed
step-replay mismatches, 35 process errors, 118 full timeouts, and 6 replay
timeouts. The 112-worker launch caused severe CPU contention, while memory
remained safe. D-012 records the C0 parsing fix.

D-013 rejects reconstructed or serialized proof-state replay as Phase 2 cost
evidence. Lean execution can depend on hidden elaborator and recursion context
that is absent from an apparently identical visible goal. Retrying a tactic
from such a state can therefore change both acceptance and cost.

D-014 defines the corrected measurement:

1. Run the unchanged complete declaration for the authoritative verdict and
   high-resolution process CPU.
2. Run the same declaration with Lean's in-process C profiler enabled.
3. Deterministically align profiler records to the frozen top-level tactic
   prefix and assign only conservative attributable cost.
4. Keep profiler overhead separate. Any unsupported or ambiguous case falls
   back to independent verification and contributes zero claimed opportunity.

The 19-proposal regression selected from every known discrepancy family passed:
19/19 unchanged full verdicts, 14/14 profile-eligible verdicts, 5 explicit
fallbacks, 32 reached units, and no errors or timeouts. It is a semantic
regression, not a representative performance sample.

## Diagnostic breadth gate

The deterministic six-shard D017 run completed all 14,496 proposals in 20.2
minutes. All full verdicts agree; all 12,758 profile-eligible verdicts agree;
1,508 fallbacks are explicit; 32,054 reached units have complete CPU telemetry;
and there are no timeout or process failures. The aggregate and hand review are
`reports/c0_replay_breadth_d017.json` and
`reports/c0_replay_breadth_d017_review.md`.

Its conservative opportunity estimate is 6.463%, with a theorem-bootstrap
interval of 5.519%–7.501%. That is below the frozen 15% threshold, but these six
shards are an operational breadth set rather than the registered complete
sample. It is a
strong warning, not the final gate decision. D017 started before the final rule
that rejects ambiguous duplicate profiler-frame alignments. That rule can only
remove opportunity, but it changes eligibility, so D017 is diagnostic rather
than the final breadth artifact.

## Complete D019 gate

D019 completed all 308,960 proposals in 3:06:50 with 32 workers. It reports
168,032 current Lean acceptances, 140,784 rejections, 124 accounted timeouts,
20 process deaths, and three historical C0-label disagreements. The profiler
itself caused zero verdict disagreement across 253,772 eligible proposals and
634,646 attributed reached units.

The registered summarizer refused a claim, as required. The diagnostic-only
decomposition estimates 3.762% exact rooted-prefix opportunity with a
3.401%–4.159% theorem-bootstrap interval. Missing CPU from 20 process deaths
makes that fraction an upper estimate. The 15% gate fails decisively, so the
version-one executor path is stopped (D-017).

## Bounded successor check

Exact completed-proof memoization reaches only 6.041% under the conservative
worst-observed representative. The slowest 0.1% of proposals consume 36.265%
of measured CPU, and timeouts alone consume 24.181%. Grouping identical tactic
edges within a theorem while ignoring state yields an unsafe 18.385%–20.685%
upper bound. A top-ten authentic visible-state census is the next bounded test
of whether divergent proofs actually reconverge before the same tactic
(D-018). Pretty goals are not full state and cannot become cache keys.

The first state-capture attempt, D020, was stopped after eight of ten theorem
reports because persistent `allTactics` snapshots accumulated across proposals.
One worker reached roughly 45 GiB RSS under its 48 GiB cap, and theorem 80508
had four process errors. Per D-019, those partial outputs are quarantined as
diagnostic-only. D021 restarts Lean for every proposal; only D021 may be
consolidated into the visible-state report.

D021 is now complete. It accounts for all 320 frozen proposals: 190 align,
130 fall back, two time out, and six exit during deterministic `allTactics`
instrumentation. All 312 available current verdicts agree with D019. A 120 GiB
retry reproduced the same four 80508 exits, so those records remain explicit
zero-opportunity fallbacks rather than being retried again (D-020).

On this deliberately high-opportunity selection, exact visible goal plus exact
tactic grouping has a 15.419% CPU upper bound, 10.011 percentage points beyond
exact prefixes on the same records. This is not a speedup or a representative
estimate. The closing-tactic subset has a 13.760% upper bound and an 8.617-point
increment, but two expensive `rfl` groups supply 6.132 of those points. D-021
therefore gates any successor on measuring the actual cost of reapplying a
kernel-checked closing certificate; full state-DAG implementation is not
authorized.

The authoritative aggregate is `reports/c0_visible_state_summary.json`,
SHA-256 `2358fb685a77ed65c9058e341fdd65695719f12399ccbaa0371c0ea624c4fbdb`.
Its summary code is clean commit `610befa`; its capture provenance is clean
commit `9ddac5f`. The corresponding hand audit is
`reports/c0_visible_state_review.md`.

## Closing-certificate feasibility

D024 tests two authentic passing pairs and one authentic fail-closed case, all
hand-audited. Ordinary Lean accepts the transferred `nlinarith` and `positivity`
certificates. Generation-plus-check
versus application-plus-check is 24.107 s versus 0.0740 s (325.6x) and 20.024 s
versus 0.738 s (27.1x), respectively. The raw `eqRefl` expression has a 9.1 ms
application tactic frame but the target declaration exceeds unchanged default
`maxRecDepth`; it is a failed hit, not a speedup.

The clean D025 rerun from commit `7424ace` completed with ordinary Lean exit
code zero in 128.511 wall seconds. It measured 325.2x and 27.1x for the same two
pairs. Its authoritative aggregate is `reports/c0_certificate_probe.json`,
SHA-256 `4a77f798236c236f874aa4e237f77c2ead835ba6d31445380d6cdc85ced72fa1`;
the ignored raw profiler log has SHA-256
`3342feac1cc3164fce80534ffd6503c61c8def3b332e3991ee5b74762fc465b9`.

The two passes establish semantic and per-hit cost feasibility, not prevalence
or aggregate speedup. D-022 advances only to exact automatic keying and a
broader frozen hit-rate/cost measurement. The probe fails closed on context,
type, or ordinary-Lean resource-limit failure.

## Automatic prevalence implementation

D-023 freezes the executable key and measurement contract. The automatic key
contains the pinned environment identity, source-location-free exact tactic
syntax, and the elaborated target abstracted over ordered user-visible locals.
Hashes only select buckets; exact structural equality, inferred proof type,
definitional equality, and ordinary Lean checking are still required. Every
miss or rejection executes the original tactic.

The paired runner preserves all 32 proposals for 128 deterministically sampled
theorems and 32 separately labeled high-opportunity theorems. Each proposal
branches from the same initialized REPL environment; only the module-level
certificate store persists. The original and cached modes record individual
verdicts, CPU, wall time, memory, timeouts, process resets, and cache events.
Implementation and unit verification are complete; authentic D026 execution
found a missing namespace-open in the REPL context. D026 step `19352896.105`
was cancelled after the partial paired check exposed massive cached-verdict
disagreement and zero events. Its raw outputs are quarantined and excluded
(D-024). The corrected run is D027; no prevalence or aggregate speedup is yet
claimed.

D027 then validated real automatic hits but exposed an over-broad multi-goal
case: a certificate for the main goal cannot replace a tactic that also closes
sibling goals. Its partial run had 36 correct-to-incorrect disagreements and
was cancelled and quarantined (D-025). The key now requires exactly one
outstanding goal; multi-goal states execute unchanged as explicit uncacheable
fallbacks. D028 is the corrected registered run.

D028 removed the multi-goal disagreements but exposed one structured-tactic
splicing error: continuation lines in a native `·` block were over-indented.
It was cancelled and quarantined with one correct-to-incorrect disagreement
(D-026). The transformer now preserves relative indentation and adds exactly
two nesting spaces. D029 is the only eligible prevalence run.

D029 completed the representative stratum with 4,096/4,096 agreement and 4.54%
paired CPU saving, below the 15% gate. Its enriched audit found two large targets
where key construction itself exceeded default `maxRecDepth` before fallback.
D-027 makes key construction transactional and restores the original tactic on
every exception. D029 remains authoritative representative evidence but is not
a complete two-stratum run; D030 is the final clean consolidation candidate.

## Final automatic-certificate decision

D030 completes the frozen representative measurement. All 128 representative
theorems and all 4,096 paired proposals are present, with 4,096/4,096 verdict
agreement and no disagreements. The automatic cache recorded 921 hits
(22.85%), but reduced paired CPU from 1,492.629 s to only 1,444.260 s: a
48.369 s or 3.2405% saving. This is far below the preregistered 15% production
gate, so the general automatic closing-certificate cache is stopped.

The enriched diagnostic completed 31/32 theorems and 992/1,024 proposals. It
showed 19.90% selected CPU saving, but is not representative and contains two
verdict disagreements from deeply nested final `rfl` wrappers. It cannot
satisfy the gate. Post-D030 instrumentation excludes source-level `rfl` from
cache attempts; that change is defensive and is not included in the measured
D030 result.

The authoritative aggregate is
`reports/c0_certificate_prevalence_d030.json`, with SHA-256
`efe23e5c17b4ab60cdc972f08bcf2cbf42a36c0deb9b3c26191c679c6a32a2a1`.
The hand audit is `reports/c0_certificate_prevalence_review.md`. The clean
measurement commit was `90e074b`; the clean summary-code commit was `657648e`.
No further broad replay or production cache implementation is authorized.

## Held-out RL arithmetic-closure benchmark

D-029 now defines the narrow successor workload without using cached timings.
C0 independent telemetry admits 505 arithmetic theorem groups whose repeated
exact final `nlinarith`, `linarith`, or `positivity` edges account
conservatively for 49.539% of 8,223.101 baseline CPU-seconds. The evaluation
input is already frozen: the corresponding 16,160 proposals in the completed
C1 GRPO-default verifier stream. Its source manifest audits 308,960 registered
proposals and the cohort contains 15,774 historically correct proposals.

Combining the slower D025 transfer anchor with 2% overhead and 100% retention
of that upper signal gives 45.7% less CPU or 1.84x CPU-equivalent throughput.
Because exact-key compatibility, first captures, and distribution shift can
only reduce retention, 1.84x is an upper-sensitivity hypothesis, not a
conservative forecast or headline result.

D-030 prohibited C1 Lean extraction, replay, paired execution, and cluster work
until an existing-artifact-only analysis supported at least 1.5x under a
conservative retention bound. That analysis is now complete. The 27 admitted
theorems already covered by D030 saved 13.892% CPU across 864 paired proposals,
equivalent to 1.161x, with 864/864 verdict agreement. Its theorem-bootstrap 95%
interval is 7.759%--20.258%, entirely below the required 36.690%.

D-031 therefore stops the C1 cohort without spending new verification compute.

## External repair corpus screen

The compute-free D-032 screen pins and analyzes APRIL and LeanPolish without
invoking Lean. APRIL has large `src_hash` groups but a median zero post-`by`
common source prefix across each group and no pinned Lean/Mathlib environment.
LeanPolish supplies authentic candidate siblings, but 11,552 cleanup rows lack
group identifiers and rejected siblings were not replayed as complete files.

Pinned Goedel sources exactly anchor 1,243 LeanPolish local-edit groups. Their
median raw proof-source prefix is 80.92%, but generated comments inflate it;
the comment-stripped non-whitespace median is 36.14%. Replacing reusable CPU
with that source-position proxy gives a hypothesis median of only 1.260x at 2%
overhead. No Lean run is authorized. The next credible input must already retain
complete repair/self-correction attempts, exact environments, ordinary Lean
verdicts, and per-tactic cost telemetry.
No C1 extraction, replay, paired benchmark, or cluster allocation is planned.
The authoritative aggregate is `reports/c0_rl_retention_gate.json`; the hand
review is `reports/c0_rl_retention_gate_review.md`.

## Exact checkpoint-branch mechanism probe

D-033 treats intentional branching from one retained Lean state as a materially
different successor to accidental prefix collisions. Its bounded local probe
uses one deliberately expensive exact prefix and 16 fixed suffixes. Shared
execution, independent replay from the theorem root, and ordinary complete
proof elaboration agree on all 16 verdicts: nine acceptances and seven
rejections, with no fallback, timeout, or process error.

On this controlled prefix-heavy construction, exact branching reduces measured
prefix-plus-suffix CPU from 0.268181 seconds to 0.048486 seconds (5.531x) and
wall time from 0.274198 seconds to 0.050326 seconds (5.448x). This is **Measured
controlled mechanism evidence**, not an authentic workload or RL speedup. D-034
prohibits broader synthetic benchmarking. The next gate requires read-only
authentic retained-state traces with at least eight suffixes per checkpoint and
at least 60% conservative common-prefix verifier CPU.

The aggregate is `reports/branch_probe_d033.json`; the interpretation is
`reports/branch_probe_d033_review.md`; the 48-record raw artifact checksum is
recorded in both. The aggregate SHA-256 is
`9f297bdebcb20c6865b7d941f324229e6e61588c9b6c088f0b598dffa4f97e97`.

## Authentic integration target

D-040 and D-041 provide a system-neutral, no-overwrite path for screening
telemetry from an already-completed run. A pinned source audit now identifies
OProver as the first credible producer integration. Its normal GRPO pipeline
creates contiguous best-of-N siblings for each theorem and independently
verifies complete proof attempts. Its pinned Lean REPL v4.15.0 already exposes
every native tactic's proof-state ID and can pickle or resume that state.

No Lean or model run was needed for this finding. OProver's server still lacks
exact process CPU at native tactic boundaries and releases each REPL after one
request. D-042 therefore authorizes capture-adapter implementation and
unit/protocol validation, not a benchmark. The public OProofs and ai4math-lean
datasets add scale and latency context but cannot support speedup claims because
they omit the required exact lineage and prefix CPU. The source-supported
adapter map is `reports/oprover_adapter_feasibility.md`.

The first adapter slice is implemented and fixture-validated. Pinned Lean and
REPL patches expose absolute CPU scopes and exact native byte ranges, and a
public Python parser fails closed unless byte range and syntax kind both match.
The patches apply cleanly to the exact OProver pins and the parser has eight
unit tests. A third pinned patch wires capture through OProver and Kimina,
isolates instrumented REPLs from the ordinary pool, preserves non-SHRED stderr,
and now implements group-scoped capture for exact rollout siblings. One batch
request leases one fresh REPL, executes every unique complete attempt from
environment `0`, and returns per-proposal group receipts. Exact duplicates are
explicitly cached; malformed IDs, theorem/header mismatches, lease loss,
missing results, and inconsistent receipts are explicit fallbacks. The client
never silently retries an uncertain group request. The changed source passes
static compilation, and the producer patch round-trips exactly against the
audited OProver commit. The OProver dependency environment was not installed,
so the new producer tests are checked in but not executed. Representative
checkpoint and environment/context receipts remain next.

**Observed validation (2026-09-01):** the pinned patched Lean 4.15.0 toolchain
and patched REPL both compiled. The checked-in three-tactic protocol validator
then found 17 native CPU boundary records, joined all three REPL tactics by
exact byte range and syntax kind, kept unrelated stderr empty, and obtained
identical native tactic output with capture disabled. The validation exposed
and fixed two pre-integration defects: Lean's ordinary trace stream is captured
as REPL diagnostics, so SHRED now writes directly to file descriptor 2; and
range-only candidate counting incorrectly treated same-range tactic wrappers as
ambiguity, so the parser now selects the exact `(range, syntax kind)` pair and
still rejects duplicate exact pairs. This is correctness validation, not a
performance experiment or benchmark.
