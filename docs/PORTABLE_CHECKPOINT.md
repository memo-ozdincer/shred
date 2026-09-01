# Portable exact checkpoint contract

Status: proposed successor design; no execution is authorized.

## Intended capability

SHRED may eventually reuse an exact Lean proof prefix across independent
attempts, processes, workers, or policy iterations. A producer executes an
unchanged prefix from a pinned theorem root and serializes the complete Lean
proof state. A compatible consumer loads that state, executes one unchanged
suffix, materializes the resulting proof into the original declaration, and
asks the ordinary Lean kernel to check the declaration.

The checkpoint is a speculative execution artifact. It is never an acceptance
certificate and never replaces ordinary Lean.

## Trust boundary

The pinned Lean REPL implements proof-state pickling with `unsafeCast` and
replays newly serialized constants into an elaboration environment without
kernel type checking. Its own source calls pickles trusted artifacts rather
than a verifier boundary. Therefore:

- accept only artifacts produced by a trusted SHRED worker in the same
  hermetic deployment;
- authenticate the producer and verify the artifact digest before any load;
- never load a user-supplied, downloaded, corrupt, or unsigned pickle;
- isolate unpickling in a disposable process with bounded memory and time;
- treat every load, compatibility, parsing, or finalization failure as an
  independent-verification fallback; and
- derive the attributable verdict only from an ordinary kernel check of the
  complete original declaration.

An artifact digest protects integrity; it does not make an untrusted pickle
safe.

## Two-level identity

The cache uses a compatibility identity and a work identity. Both are exact.

### Compatibility identity

- contract and serializer schema version;
- Lean toolchain revision and Lean binary SHA-256;
- REPL revision and binary SHA-256;
- host architecture, operating-system ABI, and hermetic image digest;
- project repository revision and clean/dirty state;
- `lean-toolchain` and `lake-manifest.json` SHA-256;
- every transitive imported `.olean` module name and SHA-256;
- every native plugin or shared library SHA-256;
- resource semantics: heartbeat, recursion, wall-time, CPU-time, memory, and
  thread limits; and
- a digest of all declared read-only external inputs available to Lean
  metaprograms.

Any absent or unequal field is a miss. Cross-architecture and cross-ABI reuse
remain disabled until separately justified by new evidence.

### Work identity

- logical module name and canonical source path;
- exact UTF-8 bytes preceding the theorem root;
- declaration kind, fully qualified theorem name, and exact statement bytes;
- command options, namespaces, sections, open declarations, scoped features,
  and local attributes active at the root;
- ordered Lean-native tactic boundaries and exact UTF-8 syntax bytes for the
  shared prefix; and
- the root and prefix lineage identifiers emitted by the producer.

Pretty-printed goals, source positions alone, tactic heads, normalized syntax,
or hashes of visible hypotheses are never cache keys.

The admission key is SHA-256 over canonical serialization of both identities.
The stored envelope also includes the pickle SHA-256, byte size, creation time,
producer identity, producer signature, and the exact source manifest.

## Unsupported cases

The first implementation must miss and independently verify when it sees:

- scoped environment extensions created during the session;
- an unknown environment extension or omitted serializer field;
- arbitrary undeclared file, network, clock, randomness, or process input;
- unsafe or partial declarations introduced by the prefix;
- an unpinned or dirty dependency;
- an unsigned artifact or producer outside the trusted deployment;
- a different Lean, REPL, project, import, plugin, option, or resource digest;
- an inability to materialize the completed proof into the original theorem;
  or
- any ordinary-Lean disagreement, timeout, crash, or accounting ambiguity.

## Finalization requirement

The pinned REPL already extracts the root proof assignment and kernel-checks an
anonymous opaque definition. The missing step is narrower: close the entire
root local context, require the original theorem name, universes, and type, and
call the kernel checker on an independently rebuilt clean pre-theorem
environment. The complete protocol and eligibility boundary are frozen in
`docs/KERNEL_FINALIZATION.md`.

Replaying constants from the pickle remains insufficient because that path
explicitly bypasses kernel checking. A shared verdict is attributable only
after exact named-theorem finalization succeeds in the clean environment.

## Novel-information gate for any future run

Hypothesis: on authentic iterative repair or cross-worker RL verification,
trusted portable checkpoints can remove at least half of total verifier CPU
and provide at least 2x verifier throughput over ideal process-local prefix
sharing while complete ordinary-Lean verdicts remain identical.

Existing evidence cannot answer this because public repair releases omit
either intermediate attempts, Lean-native boundaries, per-attempt verifier CPU,
or all three. A future run is allowed only after an existing read-only artifact
establishes all of the following:

- at least eight attempts per qualifying theorem/checkpoint group;
- at least two independent live Lean execution scopes per qualifying group;
- at least 60% conservative incremental cross-scope share of verifier CPU after
  ideal process-local prefix sharing;
- projected total capture and load overhead no greater than 0.2 complete
  independent verifications per eight-attempt group;
- enough groups for aggregate, median, tail, and per-theorem reporting; and
- verifier CPU is a material fraction of the end-to-end workload.

The implemented, system-neutral input and cost model for this gate are frozen
in `docs/AUTHENTIC_TRACE_CONTRACT.md`. `shred screen-authentic-trace` validates
and screens an already-generated artifact without loading a checkpoint or
executing Lean.

Decision map:

- If authentic reuse or verifier share misses the gate, stop the workload.
- If finalization or trust cannot preserve ordinary-Lean authority, stop the
  mechanism.
- If the gate passes but portability overhead erases 2x, retain only
  process-local branching.
- Only if all three pass may one bounded paired experiment be proposed. Its
  new question is whether trusted cross-process portability preserves the
  predicted savings and verdict equivalence, not whether more repetitions make
  D-033 statistically stronger.
