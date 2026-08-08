# Session Handoff

Last updated: 2026-08-08 17:05 Eastern

This is the authoritative operational handoff for the Lean Prefix project. It
records what is established, what is only preliminary, and the exact next run.

## Goal and scientific boundary

The project tests one mechanism:

```text
independent execution of complete Lean proof attempts
    -> exact shared-prefix-trie execution of those same attempts
```

It must not alter proofs, theorem statements, Lean acceptance, timeouts, or
proposal accounting. Version one shares only exact rooted tactic prefixes for
the same theorem and pinned environment. Unsupported syntax falls back to
ordinary independent execution.

## Repository and revisions

- Repository: `/scratch/memoozd/rl/lean-prefix`
- Remote: `https://github.com/memo-ozdincer/lean-prefix.git` (private)
- Branch: `main`
- Last implementation commit before this handoff: `e3a9131`
- Git author: `Memo Ozdincer <73766315+memo-ozdincer@users.noreply.github.com>`
- Lean workspace: `/scratch/memoozd/rl/DeepSeek-Prover-V1.5/mathlib4`
- Mathlib commit: `2f65ba7f1a9144b20c8e7358513548e317d26de1`
- Lean toolchain: `leanprover/lean4:v4.9.0-rc1`
- REPL commit: `c6199a81de2a7e16cb27d6f85f56cff7043cd27f`

The Mathlib workspace has a known modified `lake-manifest.json`; this state was
already present in the measured Phase 1 environment and is recorded by every
run. Do not silently clean or update it.

## Established evidence

The self-contained C0 discovery corpus contains 9,655 theorems, 308,992
physical proposal records, and 308,960 registered proposals after excluding 32
padding records. Of the registered proposals, 168,029 are Lean-correct.

Phase 1 measured:

- 42,815 exact duplicate proposal occurrences (13.86%);
- 304,546 conservatively parseable proposals (98.57%);
- 888,421 eligible tactic occurrences and 689,193 exact trie nodes;
- 199,228 syntactically reusable occurrences, an unweighted 1.289x oracle;
- 53.71% of eligible proposals sharing their first exact prefix.

These are syntax counts, not an acceleration result.

Phase 2 implementation is complete and has 21 unit tests plus small authentic
integration checks. On the first C0 theorem, complete replay matched 32/32 C0
verdicts; sequential replay matched 31/31 eligible complete-proof verdicts and
reached/replayed all 86 native tactic units. A separate correct bullet proof
also replayed exactly. The first theorem's reusable reached-prefix CPU share
was 8.36%, but one integration theorem is not the registered gate sample.

## Immutable and local inputs

- Manifest: `data/c0.manifest.json`
- Complete corpus: `data/c0/proofs/part-0001.jsonl.gz` through `part-0004.jsonl.gz`
- Native-unit artifact: `artifacts/c0_native_units.jsonl.gz`
- Native artifact SHA-256:
  `c53e4240355373d1b16c80634305f1b3611f6970607267479a3825ac8e3d4331`
- Phase 1 aggregate: `reports/c0_native_prefix.json`

The native-unit artifact and all replay shards are intentionally Git-ignored.
Do not delete the native artifact, and do not mistake GitHub for its backup.

## Current allocation

At handoff time:

- Slurm job: `19352896`
- Node: `c126.nibi.sharcnet`
- Account: `def-zhijing_cpu`
- Resources: 192 CPUs, `766000M` allocated RAM (755 GiB visible)
- Scheduled end: 2026-08-09 16:00:53 Eastern
- State when checked: running, with approximately 742 GiB available

This allocation is temporary operational state. Verify it rather than assuming
it remains live:

```bash
scontrol show job 19352896
ssh c126 'hostname; nproc; free -h'
```

The first Phase 2 launch was stopped before any shard completed after authentic
malformed theorem declarations exposed a missing explicit invalid-root path.
Decision D-009 and the associated tests define the correction. Empty or partial
gzip files from that stopped launch are not results and may be overwritten. A
targeted replay of proposal
`53699aeac823df1902a21420b7b6a2637343566bb4fd7a6081329c40b44ed42f`
then reproduced the full rejection and consolidated as complete with one
explicit invalid root and zero reached tactic units.

## Exact next action

First ensure this repository is clean at the final handoff commit and that the
native artifact hash matches. Then, in a persistent `tmux` session on `c126`,
run 128 deterministic shards with concurrency 112 using the commands in
`COMPUTE.md`. All outputs must remain under this repository on `/scratch`.

At 30 and 60 minutes record:

- number of completed shard reports;
- aggregate and maximum REPL RSS;
- available node memory;
- observed errors, timeouts, and verdict disagreements;
- a revised ETA based on completed work, explicitly marked preliminary.

If memory is healthy, leave concurrency unchanged. If available RAM falls below
100 GiB or Slurm/kernel memory warnings appear, stop only the worker launcher
cleanly and resume the missing shards at lower concurrency. Do not lower the
24 GiB per-process safety ceiling or change the 300-second timeout to gain
throughput.

## Completion and gate

After all shard reports exist, consolidate exactly 308,960 proposal records as
specified in `COMPUTE.md`. The summarizer must report:

- complete input accounting with no duplicate/missing IDs;
- zero full-verdict disagreements;
- zero sequential-verdict disagreements for eligible proposals;
- no missing CPU telemetry used by the cost claim;
- the reusable reached-prefix CPU fraction, per-theorem distribution, and
  theorem-bootstrap interval.

The frozen feasibility threshold is 15%. If the complete result passes, begin
Phase 3's warm independent baseline. If it fails, stop the version-one executor
path and write the characterization; do not relax exact equality or tune the
threshold after seeing the result.

Before advancing either way, hand-read the registered correct/incorrect,
cheap/expensive, failure/timeout, parser-fallback, and high-reuse strata and
update `STATUS.md` and `DECISIONS.md`.

## Recovery after interruption

Completed shards persist on `/scratch`. A shard is considered complete only
when both its gzip artifact and JSON report exist; a partial gzip without its
report should be overwritten. Use the missing-report resume command in
`COMPUTE.md`. Never rerun or overwrite completed reports casually.

Finally, hash the consolidated report and all shard artifacts, preserve a copy
outside node-local storage, commit aggregate reports and documentation, and
push `main`. Raw proposal-level replay traces remain private and Git-ignored.
