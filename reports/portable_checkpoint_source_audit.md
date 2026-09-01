# Portable checkpoint source and trace audit

Date: 2026-08-31

Evidence label: **Observed** from pinned source and public artifact schemas. No
Lean execution, proposal generation, model inference, or cluster work was
performed.

## New question

Can SHRED safely turn Lean's existing proof-state serialization into exact
reuse across independent attempts or workers, and is there an existing
authentic artifact that justifies implementing it?

This is new relative to D-033: the controlled probe reused an in-memory state
inside one process. Portable reuse crosses process or time boundaries and adds
serialization, compatibility, trust, and finalization risks.

## Pinned Lean REPL audit

Source: `leanprover-community/repl` at
`5d5c49d13dfc0c1d2df43a27c3e56e02ad81b9c3`, using
`leanprover/lean4:v4.34.0-rc2`.

### What is actually serialized

`REPL/Snapshots.lean` serializes imports, new constants, compacted core/meta/
term/tactic state and context, the tactic goals, and root goals. It deliberately
omits environments reconstructed from imports, closures, logs, info trees,
traces, and several caches. On load, imports are reloaded and the serialized
constant delta and proof state are reconstructed.

The repository contains paired regression inputs in which one REPL process
creates `test/d.olean` and a later fresh REPL process loads it and completes the
proof. This directly supports same-repository, same-build, same-host
cross-process feasibility. The README says transfer to another machine should
work when the same imports are available, but the pinned repository does not
contain a cross-machine or cross-architecture result. Treat that claim as a
hypothesis, not measured evidence.

### Safety and compatibility findings

- `REPL/Util/Pickle.lean` loads module data with `unsafeCast`; a malformed file
  may have the wrong type and cause crashes or worse behavior.
- `REPL/Lean/Replay.lean` inserts serialized constants without kernel checking
  and explicitly says pickles are trusted artifacts, not a verifier boundary.
- Constant replay uses a private Lake FFI export described by the source as
  unstable and on a deprecation path.
- Only constants are replayed. Environment extension entries are omitted.
  Scoped extensions and scoped notation created in-session are a documented
  limitation.
- The tactic-mode implementation already extracts the assigned root proof and
  kernel-checks an anonymous opaque definition. It does not yet require the
  original theorem name, universes, and type or an independently rebuilt parent
  environment; the initial audit overstated this as a wholly absent bridge.
- Providing a command environment while loading a proof state is supported,
  but compatibility is the caller's responsibility; the protocol does not
  authenticate the file or verify complete dependency digests.

### Portability assessment

| Boundary | Evidence | Assessment |
| --- | --- | --- |
| Reuse within one live process | D-033 controlled probe | Mechanism works; authentic value unknown |
| Fresh process, same pinned build and host | Official paired regression inputs and expected outputs | Supported by source-level test coverage |
| Different worker with identical hermetic image | Inference from fresh-process test | Promising hypothesis; require signed producer and exact identity |
| Different machine with same imports | README statement | Hypothesis only |
| Different architecture, ABI, Lean, REPL, plugin, or import build | No supporting evidence | Mandatory miss |
| Session-created scoped extensions | Documented omission | Mandatory miss |
| Untrusted or downloaded pickle | Explicit unsafe trust boundary | Never load |
| Final attributable ordinary-Lean theorem verdict from loaded completion | Anonymous-definition kernel check exists; exact named clean-environment protocol is designed but unimplemented | Bounded engineering gap; workload gate still blocks implementation |

## Authentic trace audit

### OProver

Pinned source: `multimodal-art-projection/OProver` at
`b0cb2583b702d5040f84783ebba23d86241eac05`.

The inference harness creates separate JSONL files for each refinement round.
Its validation record includes candidate code, previous-round proof text,
success, error type/messages, timestamp, and verifier wall time. This is a
strong potential future integration point because attempts are deliberately
related across rounds rather than accidentally colliding.

However, no completed inference output shards are committed. The public
OProofs release at revision
`3bae0c06157639c0a673679635c669d19c99e906` exposes 6,804,694 rows with only
`formal_statement`, `formal_proof`, `cot_proof`, and `prompt`. It omits the
intermediate attempts, round lineage, errors, timings, Lean/Mathlib revision,
and native tactic boundaries. The verifier service records whole-request wall
time; its published round record does not contain per-tactic CPU.

### Later repair-trace candidates

Two later candidates also stop before a run. FormalMath's published repair
schema lacks attempt lineage, exact environment identity, and verifier CPU, so
its 1.15 GB corpus was not bulk-downloaded. The trace-level attribution study
describes raw agent/tool/compiler JSONL with timing, but its public conference
and author pages expose only the paper and no trace artifact. Details and the
pre-registered outcome map are in
`reports/authentic_repair_trace_gate_review.md`.

A subsequent broader search found authentic GRPO, replay-buffer, and full
compiler-feedback agent traces. Leanstral 1.5 is the richest available archive,
but its per-attempt metadata and streams omit process CPU and native checkpoint
identity. D-040 therefore adds a neutral existing-run export contract rather
than downloading or replaying these corpora.

### Previously audited sources

- Lean-Prover's code writes timestamped local session JSONL, but no user session
  corpus is committed and its records do not isolate prefix and suffix CPU.
- APRIL supplies systematic erroneous/correct pairs rather than authentic
  iterative attempts from one retained root and has no per-tactic cost.
- BFS-Prover-V2 and nanoproof are live-tree systems that already reuse their
  retained state; their public repositories do not include the required
  complete timing-rich run artifacts.
- LeanTree and LeanProgress omit either alternative sibling attempts or the
  referenced trajectory artifact and cost fields.

## Gate result

**Observed:** the portable primitive is real enough to warrant a complete
design, but no public artifact passes the workload gate. Zero audited releases
combine authentic related attempts, exact environment identity, Lean-native
boundaries, every verdict, and per-attempt verifier CPU.

**Decision:** do not implement or benchmark portable caching yet. The
proof-materialization/kernel-finalization design is resolved statically in
`docs/KERNEL_FINALIZATION.md`; implementation still requires an existing
read-only trace artifact satisfying the gate in `docs/PORTABLE_CHECKPOINT.md`.
Any producer can now supply such evidence through
`docs/AUTHENTIC_TRACE_CONTRACT.md` without rerunning Lean.

This outcome is informative rather than a request for more statistical power:
it identifies two new qualitative blockers—trusted unsafe deserialization and
missing ordinary-kernel finalization—that D-033 could not expose.
