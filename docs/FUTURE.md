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
