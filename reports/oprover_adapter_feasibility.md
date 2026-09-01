# OProver authentic-checkpoint adapter feasibility

Date: 2026-09-01

Evidence label: **Observed** from pinned source and public metadata. No Lean
execution, model inference, rollout generation, or bulk dataset download was
performed.

## New question

Can a widely applicable RL proof-repair system produce SHRED's exact
existing-run telemetry with a narrow instrumentation change, without changing
its proposals, theorem statements, timeouts, or ordinary Lean verdicts?

Existing audits could not answer this. They inspected OProver's released proof
pairs and current JSONL outputs, but not the exact Lean REPL revision pinned by
its verifier or the ordering of rollout siblings at the verification boundary.
The outcome changes the project decision: a narrow adapter makes authentic
evidence collectible during a normal future OProver run, whereas a missing
native checkpoint primitive would stop this integration.

## Source result

OProver revision `b0cb2583b702d5040f84783ebba23d86241eac05`
pins `leanprover-community/repl` branch `v4.15.0`; that branch resolves to
`21966799da3691a0912b5a15193585bd2dd7165d`.

The pinned REPL already supports all of the hard Lean-native state operations:

- `allTactics` returns every native tactic's exact source range, goals, and a
  process-local `proofState` ID from the command's real info tree;
- the process retains the corresponding `ProofSnapshot` values;
- a selected snapshot can be pickled; and
- a later tactic can execute from an exact retained or unpickled snapshot.

OProver already expands each prompt into `n_rollouts` contiguous candidates.
Its IDs preserve round, prompt, and rollout attribution as
`r{round}_p{prompt}_s{rollout}`. Verification is of independently generated,
complete proof attempts under ordinary Lean. This is the intended SHRED
intervention, unlike BFS-Prover-V2 and nanoproof: those systems already apply
many tactics from one live search node, so their normal fanout is not newly
accelerated independent execution.

## Exact adapter boundary

The existing OProver client sends each candidate as a separate asynchronous
HTTP request. The server obtains a REPL with the matching import header, runs
the body from environment `0`, and immediately releases the REPL. It reports
whole-request wall time and a sampled maximum CPU percentage. Those fields are
not the process CPU seconds required by SHRED's gate.

The smallest honest capture adapter has five parts:

1. Preserve the existing same-theorem rollout grouping at the server boundary
   and lease one representative REPL until the group has been classified.
2. Forward `allTactics: true` for unchanged complete attempts and return their
   native tactic ranges and proof-state IDs.
3. Sample the existing process-tree CPU counter immediately before and after
   every complete request, returning the delta rather than `cpu_max`.
4. Add a native tactic-boundary process-CPU clock. Record cumulative process
   CPU when each real tactic begins or ends; do not allocate whole-request CPU
   using wall-time shares.
5. After exact same-root prefix comparison, pickle only the selected
   representative checkpoint and emit its digest plus exact parent-environment,
   root-context, and ordered-prefix receipts. Every non-eligible attempt remains
   an explicit fallback with its complete verdict and CPU.

The source-only reference implementation now covers the hard timing boundary:

- `integrations/oprover/lean4-v4.15.0-shred-cpu-boundaries.patch` uses Lean's
  existing RAII profiling scopes to emit absolute process-plus-completed-child
  CPU for every request parsing/elaboration scope and exact tactic source byte
  range;
- `integrations/oprover/repl-v4.15.0-native-byte-ranges.patch` adds the original
  syntax kind and byte range to `allTactics`; and
- `shred.oprover_adapter` strips those records from stderr, preserves all other
  stderr, and joins a tactic only when both its native byte range and syntax
  kind match exactly.
- `integrations/oprover/oprover-kimina-cpu-capture.patch` creates a separate
  capture-enabled REPL pool, forwards the opt-in request through Kimina and
  OProver, and retains either the native telemetry or an explicit capture
  fallback in the existing verification result.

All three patches apply cleanly to the frozen source revisions. The Kimina and
OProver Python changes pass static compilation, and seven parser tests cover
successful cumulative attribution plus multi-command envelopes, malformed,
missing, duplicate, text-only, and syntax-conflict failures. This is source
validation, not a compiled or executed Lean result.

The group lease is an efficiency measure, not an authority boundary. The
captured artifact remains trusted producer telemetry, and any later executor
must still perform the named clean-environment kernel finalization specified in
`docs/KERNEL_FINALIZATION.md`.

## Why no run is authorized yet

The native checkpoint and workload-shape risks are resolved statically. The
remaining uncertainty is instrumentation correctness, not whether another
seed or larger sample changes the result. Wall time, one-second CPU sampling,
or SHRED's earlier profiler-based CPU allocation cannot be substituted for
same-attempt prefix process CPU.

The next work is therefore group leasing, receipts, and compile/protocol
validation. Only a
normal authentic run that already has a substantive RL purpose may emit the
new sidecar. Its sealed, read-only telemetry must pass D-040 before any SHRED
paired benchmark is proposed. No OProver reproduction run or dataset-scale
verification is authorized solely to populate the gate.

## Other public data distributions

The current public OProofs revision
`d3bb4410c8715eb449206e6c2fbf8cbb1a8bd7b8` has 6,804,694 theorem-proof rows,
but only final proof-pair fields. It remains useful for estimating how often a
theorem has multiple published proofs, not for executable checkpoint or CPU
claims.

The newly published `ai4math-lean` revision
`6735c2403f2c57bcd5e9b7aab572872d8265d7d9` contains 3,394,310 problems from
21 Lean datasets, with proof bodies, verification results, and Lean 4.21 wall
latency. This is a broad and potentially useful distribution for finding
expensive verification families. It has neither authentic sibling-attempt
lineage nor native prefix CPU, so its latency must not be presented as SHRED
speedup evidence. A future producer can use it as theorem input only if the
actual multi-attempt run supplies the missing exact telemetry.

## Decision map

- If the adapter can return exact boundary CPU, stable lineage receipts, and
  one verdict per unchanged input, integrate it into a normal OProver run and
  screen the immutable sidecar.
- If native boundary CPU cannot account for the process tree or the group lease
  changes execution semantics, stop the adapter rather than accepting proxy
  timing.
- If an authentic sidecar later passes the frozen two-times value gate, propose
  one bounded independent-versus-shared comparison.
- If it fails, stop this workload and retain the adapter only as diagnostics;
  do not add seeds merely to improve significance.
