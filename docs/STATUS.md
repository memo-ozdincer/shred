# Project Status

Last updated: 2026-08-08

## Complete

- Private, self-contained repository with all four audited C0 shards.
- Exact C0 count reproduction: 9,655 theorems, 308,960 registered proposals,
  168,029 correct proposals, and 32 separately excluded padding proposals.
- Stable proposal identities tied to immutable source-content hashes.
- Exact complete-proof reuse analysis.
- Pinned Lean-native top-level tactic extraction with explicit conservative
  fallback and a deterministic proposal-level artifact.
- Full C0 syntax characterization and deterministic 18-case hand review.
- Pre-registered 15% reached-prefix CPU-time gate.

## Implemented and integration-tested

- Persistent pseudo-terminal client for the pinned DeepSeek REPL. The terminal
  is required because this upstream REPL buffers ordinary-pipe output.
- Full-proof replay from a shared imported environment.
- One immutable root proof state per theorem, with each proposal replayed as its
  exact native units until completion or first failure.
- Per-reached-tactic wall time, process CPU, peak RSS, heartbeat, result, and
  prefix telemetry.
- Deterministic theorem sharding, process restart, timeout/failure accounting,
  and 24 GiB default process limits.
- Shard consolidation, duplicate detection, verdict-agreement enforcement,
  cost-weighted exact-prefix oracle, theorem bootstrap, and gate evaluation.

## Next evidence

The first 32-attempt theorem reproduces all 32 frozen C0 verdicts; all 31
eligible proposals reproduce the complete-proof verdict under sequential
replay, with all 86 native units reached and replayed. A separate correct
`Lean.cdot` bullet proof also replays exactly. The largest observed persistent
REPL RSS in these checks is 3.71 GiB. These are integration checks, not a
performance sample.

Run the complete Phase 2 replay on the allocated 192-core standard-memory CPU
node, consolidate all 308,960 proposal records, and hand-read the registered
cost strata. Do not begin the shared executor unless the consolidated report
is complete, has zero verdict/sequential disagreements, and passes the frozen
15% cost-opportunity gate. See `SESSION_HANDOFF.md` for the current allocation
and `COMPUTE.md` for commands and recovery.

The first full-corpus launch on `c126` exposed two independent replay-adapter
gaps. Decision D-009 records fail-closed handling for theorem declarations Lean
rejects before tactic mode. Six subsequently completed diagnostic shards
(14,496 proposals) reproduced every full C0 verdict but had 724 sequential
disagreements. Decision D-010 records the raw-protocol diagnosis and minimal
pinned REPL patch. Its six-case regression has 6/6 complete-verdict agreement,
4/4 sequential agreement for replay-eligible proposals, two explicit
structural fallbacks, and no errors or timeouts. The first corrected breadth
rerun preserved 14,496/14,496 full verdicts and reduced sequential disagreements
from 724 to 98. D-011 records the two residual raw-protocol causes and their
narrow correction. Its exact three-proposal regression has 3/3 full and
sequential agreement, one explicit invalid root, and two explicitly counted
heartbeat-uninstrumented `<;>` units. The final six-shard breadth gate then
passed: 14,496/14,496 full verdicts and 14,152/14,152 replay-eligible
sequential verdicts agree, with no failures, missing CPU telemetry, or duplicate
proposal IDs. Its 11.74% opportunity estimate is diagnostic, not the registered
gate result, because these six shards were selected through earlier completion.
The remaining 122 shards are now the next evidence-producing run.

A subsequent uniform full-corpus launch completed all 128 shards and 308,960
unique proposal IDs under commit `4a7e7b2`. It is diagnostic, not a cost result:
the summarizer correctly refused the claim after finding 36 full C0-label
disagreements, 72 sequential disagreements, 35 REPL process errors, 118 full
timeouts, and 6 replay timeouts. D-012 records the exact C0 parsing and
early-completion causes identified from this census. Heavy 112-way contention
also makes that concurrency unsuitable for the final measurement despite safe
memory use.
