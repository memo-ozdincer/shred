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

Status: complete; the registered gate failed and the executor path stopped.

- Preserve an unchanged complete-proof request as the verdict and CPU baseline.
- Collect per-tactic exclusive timing in the same declaration with Lean's
  in-process profiler, without wrapping or resubmitting individual tactics.
- Align only a deterministic reached top-level prefix and treat unattributed
  work and unsupported structures conservatively.
- Measure which reused prefixes contain expensive computation.
- Estimate achievable CPU-time, wall-time, and memory savings with confidence
  intervals or complete-corpus aggregation where feasible.
- Separately quantify whole-proof memoization and batch-barrier effects.

Gate: proceed to the engine only if exact prefix reuse has a material,
cost-weighted opportunity on authentic data. Record the threshold before seeing
the final weighted result; do not tune it post hoc.

The threshold was frozen at 15% of independent full-verification CPU time in
Decision D-005. Earlier reconstructed-state estimates are diagnostic only and
are superseded by D-013 and D-014. Only the corrected complete-corpus result is
the registered gate result.

D019 covers all 308,960 proposals. Its strict summary is invalidated by three
historical-label disagreements and 20 process deaths, while its
diagnostic-only exact-prefix estimate is 3.762% (bootstrap 3.401%–4.159%).
Missing failure CPU can only lower the true fraction. D-017 therefore stops
the plan here; Phases 3–6 are not authorized for the version-one mechanism.

## Post-gate successor diagnostic

Status: bounded visible-state census complete; implementation not authorized.

D021 captured the frozen top-ten high-opportunity theorems with a fresh Lean
process per proposal. Its visible-state upper bound is 15.419%, but the sample
is intentionally enriched and pretty goals omit hidden state. The next gate is
not a semantic-state engine: D-021 permits only an exact closing-certificate
application benchmark on hand-audited groups. It must measure ordinary Lean's
full elaboration and kernel-check cost and fail closed on unmatched contexts.

## Phase 3 — Reference baseline

Status: stopped by the Phase 2 gate.

- Build a warm, persistent, independently executing Lean baseline.
- Freeze its API, environment, resource limits, and telemetry schema.
- Demonstrate stable ordinary-Lean verdicts and repeatable performance.

Gate: baseline correctness and variance are understood.

## Phase 4 — Minimal prefix-trie executor

Status: stopped by the Phase 2 gate.

- Construct a trie from Lean-native tactic units.
- Execute each eligible unique edge once.
- Snapshot the resulting proof state and fork child edges.
- Preserve proposal attribution and independently verify completed leaves.
- Route unsupported constructs through the frozen baseline.

Gate: correctness, isolation, timeout, cancellation, and accounting tests pass.

## Phase 5 — Primary evaluation

Status: stopped by the Phase 2 gate.

- Compare identical ordered proposals on identical hardware.
- Report verdict agreement before speed.
- Report wall time, CPU time, throughput, peak memory, and tail latency.
- Report savings by theorem, tactic family, prefix depth, and proposal budget.
- Evaluate on a held-out workload after implementation choices are frozen.

Gate: make only claims supported by the registered comparison.

## Phase 6 — Production hardening

Status: stopped by the Phase 2 gate.

- Stable Python and batch interfaces.
- Crash recovery and bounded caches.
- Structured metrics and trace export.
- Containers and pinned toolchain installation.
- Compatibility adapter for one real rollout pipeline.
