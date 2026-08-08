# Gated Plan

Each phase produces an auditable artifact and ends with a decision. Later phases
do not begin merely because the implementation is interesting.

## Phase 0 — Corpus integrity

Status: complete.

- Reproduce 9,655 theorems, 308,960 registered proposals, 168,029 correct
  proposals, and 32 excluded padding proposals.
- Verify every source SHA-256 in `data/c0.manifest.json`.
- Save a machine-readable audit report and checksum outside Git's raw-data
  exclusions.

Gate: exact agreement with the authoritative C0 validation.

## Phase 1 — Exact-reuse characterization

Status: complete. See `reports/c0_exact_analysis.json`,
`reports/c0_native_prefix.json`, and `reports/c0_hand_review.md`.

- Define tactic boundaries using Lean itself.
- Measure parser eligibility and fallback coverage.
- Measure complete-proof duplication and rooted prefix reuse by depth.
- Report per-theorem distributions and proposal-budget curves.
- Hand-read a fixed, stratified sample and record discrepancies.

Gate: the measured reuse must be real under Lean-native parsing, not an artifact
of whitespace removal or heuristic line grouping.

## Phase 2 — Cost-weighted oracle

Status: implementation and small integration checks complete; full-corpus
measurement next.

- Add per-tactic queue, execution, state-size, outcome, and timeout telemetry to
  an independent replay harness.
- Measure which reused prefixes contain expensive computation.
- Estimate achievable CPU-time, wall-time, and memory savings with confidence
  intervals or complete-corpus aggregation where feasible.
- Separately quantify whole-proof memoization and batch-barrier effects.

Gate: proceed to the engine only if exact prefix reuse has a material,
cost-weighted opportunity on authentic data. Record the threshold before seeing
the final weighted result; do not tune it post hoc.

The threshold was frozen at 15% of independent full-verification CPU time in
Decision D-005. The 32-proposal first-theorem check measured 8.36%, but it is a
single theorem selected for integration and is neither representative nor the
registered gate result.

## Phase 3 — Reference baseline

- Build a warm, persistent, independently executing Lean baseline.
- Freeze its API, environment, resource limits, and telemetry schema.
- Demonstrate stable ordinary-Lean verdicts and repeatable performance.

Gate: baseline correctness and variance are understood.

## Phase 4 — Minimal prefix-trie executor

- Construct a trie from Lean-native tactic units.
- Execute each eligible unique edge once.
- Snapshot the resulting proof state and fork child edges.
- Preserve proposal attribution and independently verify completed leaves.
- Route unsupported constructs through the frozen baseline.

Gate: correctness, isolation, timeout, cancellation, and accounting tests pass.

## Phase 5 — Primary evaluation

- Compare identical ordered proposals on identical hardware.
- Report verdict agreement before speed.
- Report wall time, CPU time, throughput, peak memory, and tail latency.
- Report savings by theorem, tactic family, prefix depth, and proposal budget.
- Evaluate on a held-out workload after implementation choices are frozen.

Gate: make only claims supported by the registered comparison.

## Phase 6 — Production hardening

- Stable Python and batch interfaces.
- Crash recovery and bounded caches.
- Structured metrics and trace export.
- Containers and pinned toolchain installation.
- Compatibility adapter for one real rollout pipeline.
