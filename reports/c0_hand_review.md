# C0 Native-Parsing Hand Review

Date: 2026-08-08

Artifact reviewed: `reports/c0_review_sample.json` (18 deterministically selected
examples from all 308,960 joined proposals). Selection covers correct and
incorrect proofs, deepest sharing, exact duplicates, no sharing, longest
sequences, structured syntax, every fallback class, telemetry tails, and the
highest-reuse theorem.

## Findings

- Lean-native units match the visible top-level tactic structure in the
  eligible examples. Nested `by` proofs stay inside their parent tactic; they
  are not incorrectly promoted to root edges.
- The 20-edge correct duplicate for `lean_workbook_plus_21880` is genuine, but
  also shows that some prefix opportunity is ordinary complete-proof
  duplication. The reports therefore keep whole-proof and prefix accounting
  separate.
- The 78-unit incorrect example is a long repeated `rw`/`norm_num` script.
  Syntax parsing is sound, but ordinary Lean may fail before its later units.
  Counting every parsed unit would overstate executable work; Phase 2 must
  record reached units.
- The longest correct proof has repeated internal blocks but a unique first
  edge. A rooted trie correctly finds no reuse; version one must not share
  non-rooted substrings.
- Structured `cases'`, bullets, and nested `have ... := by ...` examples retain
  their scope inside the reported units. The engine still needs execution-level
  scope and goal-isolation tests before accepting these as shareable states.
- The correct bracketed-root example and correct semicolon example justify
  conservative fallback. In particular, `exfalso; linarith` cannot be treated
  as two ordinary sequential edges without changing semicolon semantics.
- Malformed and unknown-tactic fallback examples are authentic invalid model
  outputs, not parser crashes. They remain attributable independent-verifier
  inputs.
- The theorem with the maximum 4.667x unweighted ratio consists largely of
  one-unit proofs. This is real reuse, but principally whole-proof memoization;
  it is not evidence that deep snapshotting is valuable.
- Available verifier telemetry contains severe tails: the selected correct
  `field_simp`/`ring` proof took 222.8 seconds and the selected incorrect
  one-unit `simpa` proof took 300.1 seconds. Neither selected proof has a shared
  first edge, illustrating why tactic counts cannot predict time savings.

## Review decision

Phase 1 passes its syntax-validity gate: exact rooted reuse persists under the
pinned Lean parser and the exclusions are explicit. The evidence does **not**
yet pass the performance gate. Proceed only to cost-weighted, reached-tactic
replay; do not build or advertise the shared executor from the unweighted
1.289x oracle ratio.
