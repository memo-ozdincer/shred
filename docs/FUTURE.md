# Deferred Ideas

These ideas may be valuable, but they are outside the primary version-one
claim. Keeping them here prevents accidental scope expansion.

- Merge states reached by different tactic prefixes after proving state
  equivalence.
- Normalize or canonicalize tactic syntax for broader cache hits.
- Persist prefix states across batches or policy iterations.
- Reuse computation across different theorem statements.
- Cost-aware trie scheduling and speculative execution for stragglers.
- Multi-node and hosted serving.
- vLLM-compatible continuous admission and paged proof-state storage.
- GPU or native acceleration for certificate-producing arithmetic tactics.
- Learned tactic-cost or timeout prediction.
- Integration with interactive tree search and partial-proof generation.
- State compression, eviction policies, and distributed content-addressed
  caches.
- Rich training signals derived from partial proof progress.

## Post-D019 triage

D019 eliminates exact rooted-prefix execution as version one: its
diagnostic-only opportunity is 3.762%, far below the frozen 15% gate. Exact
completed-proof memoization is also too small alone at 6.041% under a
worst-observed representative.

Two observations merit bounded checks rather than immediate projects:

- Exact tactic edges grouped within a theorem but without a state key have an
  18.385%–20.685% cost upper bound. A top-ten authentic visible-state census
  tests whether different prefixes reconverge before the same tactic. Visible
  goals omit hidden state, so even a positive result would still require a
  full-state identity and verdict-equivalence design.
- The slowest 0.1% of proposals account for 36.265% of measured CPU. This is a
  strong workload characterization, but asynchronous scheduling and straggler
  isolation are established systems techniques. Novelty and a
  correctness-preserving way to reduce total work must be shown before this is
  called a successor project.

The 2026 proof-state snapshotting work accelerates branching from an already
captured state. A possible state-DAG direction would instead detect branches
that diverge and later reconverge, then memoize an exact transition. Treat the
distinction as a hypothesis until the visible-state census and a full-state
feasibility review support it.

D021 finds real visible reconvergence in the deliberately enriched top-ten
sample: a 15.419% state-edge upper bound, 10.011 points beyond exact prefixes.
Hand review shows different model-generated preambles washing out before the
same `positivity`, `ring_nf`, `nlinarith`, or `rfl` call. This keeps the
successor hypothesis alive, but does not make pretty goals safe cache keys.

The narrow closing-certificate experiment passes for authentic `nlinarith` and
`positivity` pairs (D-022). The reduction-heavy raw `eqRefl` expression reaches
a cheap application tactic frame but its target declaration exceeds unchanged
default `maxRecDepth`, so it remains fallback. The next uncertainty for the
supported cases is safe hit prevalence. Arbitrary state transformations and
alpha-normalized context matching remain separate future ideas.

## Ranked alternatives after D024

The closing-certificate cache is now the leading successor. Continue exploring
these adjacent directions without merging them into the next experiment:

1. **Named reduction certificates or kernel memoization.** D024 shows a large
   repeated reduction/checking cost and also shows that inlining the raw proof
   can exceed `maxRecDepth`. A named auxiliary declaration may keep target
   checking shallow; changing trusted kernel caches is much higher risk.
2. **Non-closing transition certificates.** Reusing `ring_nf` transformations
   could capture more reconvergence, but mapping resulting subgoals and proof
   state is substantially harder than transferring a closing proof.
3. **Exact whole-proof memoization.** Its measured 6.041% upper bound is too
   small as a standalone paper, but it is a simple production fast path beside
   certificate reuse.
4. **Straggler-aware scheduling.** The slowest 0.1% consume 36.265% of D019 CPU.
   Continuous admission can improve wall time, but does not remove work and is
   an established systems technique.
5. **Tactic-specific native or GPU acceleration.** Potentially useful for
   arithmetic certificate generation, but broader and currently less directly
   supported by this corpus than certificate reuse.

Lean's existing incremental `checkpoint` tactic cache is architectural prior
art, not the same mechanism: it reuses the same metavariable and source
position during editing, whereas D024 transfers a generalized proof between
separate proposal elaborations after different histories.

An item moves into scope only through a recorded decision after the primary
method is measured and understood.

## Priority after D030

D030 closes the general automatic-certificate question negatively: 22.85% of
representative proposals hit, yet total paired CPU fell only 3.2405%. Most hits
are too cheap to matter. The enriched diagnostic nevertheless identifies a
small expensive tail where transferring a previously checked closing proof can
save tens or hundreds of seconds.

The highest-leverage successor is therefore not broader semantic grouping. It
is a deliberately narrow, cost-aware design that stores certificates behind
named shallow declarations and admits only tactic families and targets shown
to dominate runtime. It must pre-register its selection rule, count misses and
fallbacks, exclude raw `rfl` wrappers unless ordinary Lean validates them under
unchanged limits, and earn its own representative end-to-end gate. Until that
design exists, it remains a future add rather than production scope.

## Resolution after D031

D-029 instantiated the narrow idea as a 505-theorem arithmetic-RL cohort, but
D-030 required existing evidence to justify its compute first. The 27 admitted
theorems already covered by D030 saved only 13.892% paired CPU, with a
theorem-bootstrap upper bound of 20.258%. That is decisively below the 36.690%
reduction required for the 1.5x theory gate. D-031 stops the C1 run without new
Lean or cluster work.

Named shallow declarations might reduce application cost on successful hits,
but they do not solve the observed exact-key miss and first-capture burden.
They remain a future mechanism idea, not a pending experiment. Reopening them
requires a materially new compute-free argument rather than a narrower
post-hoc selection of positive D030 cases.

## Resolution after D035

The exact checkpoint-fork probe works, but current tactic-tree systems already
fan tactics out from a retained live state. That makes integration useful
engineering, not by itself the strongest SHRED research claim. A read-only
audit of BFS-Prover-V2, nanoproof, LeanTree, LeanProgress, and Lean-Prover found
no committed completed artifact with full sibling lineage, all verdicts, and
per-edge verifier CPU, so no authentic gate can be computed without collecting
new data.

The higher-value successor is exact reuse beyond one live search tree: across
independent attempts, workers, or policy iterations, or intentional
checkpointing for localized repair. This is distinct from reconstructing a
state from its pretty-printed goals, which D013 already showed is unsafe for
evidence. Any proposal must first define full hidden-context identity,
attribution, isolation, timeout behavior, eviction, and ordinary-Lean fallback,
then demonstrate a compute-free opportunity bound from an existing artifact.

## Portable checkpoint resolution after D037

Lean's official REPL provides a stronger primitive than goal reconstruction:
it serializes full command and proof snapshots and has source-level regression
coverage for loading a partial proof in a fresh process. This makes exact
cross-worker reuse technically plausible. SHRED's possible contribution is not
inventing serialization; it is a safe content-addressed runtime with hermetic
identity, trusted-producer authentication, isolation, explicit misses, and
ordinary-kernel finalization.

The loader remains explicitly unsafe and replays constants without checking
them, so downloaded or user-supplied artifacts are categorically out of scope.
D038 narrows the other blocker: the REPL already extracts and kernel-checks a
completed proof as an anonymous opaque definition. Exact finalization can use
the original theorem identity and type, full root-local-context abstraction,
and a clean pre-theorem environment. No new trusted Lean primitive appears
necessary, although the protocol remains unimplemented pending authentic
workload evidence.

OProver's multi-round repair harness is the best identified authentic workload:
its local per-round records include related candidate text, feedback, verdict,
and verifier wall time. The public OProofs release drops those intermediate
records and native cost data, so it cannot pass the gate. Revisit this direction
only with an existing full run artifact or after finalization becomes safely
available; do not create synthetic repetitions to demonstrate already-known
cross-process loading.

D-042 narrows this from a data-access hope to a concrete producer adapter. The
exact Lean REPL version pinned by OProver already supplies `allTactics`, native
proof-state IDs, snapshot pickling, and execution from a snapshot. OProver also
keeps each prompt's best-of-N rollouts contiguous in a verification chunk. The
remaining additions are a group-scoped REPL lease, exact full-request and
native-boundary process CPU, selective checkpoint receipts, and complete
fallback export. Implementing those capture hooks is more generalizable than a
new SHRED-only dataset run because it can evaluate normal future RL workloads
without changing their attempts.

The 3.39-million-row ai4math-lean release is a useful new distributional lead:
it spans 21 datasets and publishes proof bodies, validity, and Lean 4.21 wall
latency. It can identify expensive theorem families or seed a future authentic
multi-attempt producer, but single-row wall latency is not executable prefix
reuse evidence. OProofs similarly supplies 6.80 million final proof pairs but
not the intermediate attempt lineage or native CPU needed by D-040.

The agentic trace-level attribution study (`ShhLinF41r`) describes an even
closer artifact—raw model, tool, compiler, verdict, and timing traces—but does
not currently expose the JSONL publicly. FormalMath is publicly downloadable
and repair-oriented, but its schema omits executable lineage, environment
identity, and verifier CPU. D-039 therefore stops both without a bulk download
or reproduction run.

A later search found several public multi-turn corpora, including authentic
GRPO rollouts and Leanstral's complete compiler-feedback archives. They improve
structural availability but still omit either Lean-native checkpoint identity
or verifier CPU. D-040 turns that repeated integration gap into a public trace
contract and read-only screener. The fastest route to an implementation decision
is now for any producer with existing internal telemetry to normalize it to
that contract; no SHRED rerun is required.
