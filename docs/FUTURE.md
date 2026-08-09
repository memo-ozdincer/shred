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

The narrowest next experiment is a closing-certificate cache (D-021): reuse a
generated proof only when the goal and local context match exactly, then let
ordinary Lean check it. The apparent closing opportunity is dominated by two
very expensive `rfl` groups, where definitional equality and kernel reduction
may remain expensive even with a cached term. Measure that cost before building
a general library. Arbitrary state transformations, alpha-normalized context
matching, and kernel-level normalization memoization remain separate future
ideas, not inferred features of the current repository.

An item moves into scope only through a recorded decision after the primary
method is measured and understood.
