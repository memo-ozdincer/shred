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

The first 32-attempt theorem and a separate correct bullet-structured proof
both reproduce their full-proof verdicts under sequential replay. Run a larger
stratified integration set, then the complete Phase 2 replay on a high-memory
192-core CPU node. Do not begin the shared executor until the consolidated
report passes the pre-registered gate.
