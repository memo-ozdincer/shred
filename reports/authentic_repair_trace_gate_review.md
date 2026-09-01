# Authentic repair-trace gate review

Date: 2026-08-31

Evidence label: **Observed** public metadata, schema, and release-surface audit.
No bulk dataset download, corpus scan, model generation, or Lean execution was
performed.

## Novel question and decision map

Question: does a newly identified public repair or agentic-proof artifact make
portable exact checkpoints valuable enough to implement before any benchmark?

Existing evidence covers whole-proof final releases and live in-process proof
trees, but not authentic independent attempts that repeatedly preserve an
exact Lean-native prefix. The result could change the project decision:

- If no attempt lineage or verifier timing is public, stop without downloading
  or implementing anything.
- If lineage exists but environment identity or verifier CPU is absent, retain
  the source only as a structural candidate; do not project a speedup.
- If exact lineage, environment identity, every verdict, and verifier CPU are
  public, authorize a read-only screen for the frozen >=2x gate.

## FormalMath reasoning data

The Hugging Face API reports revision
`7e42c6b6c637d9c0fc7cf36915200b484f98aaa5`, 65,652 train rows, 66,593 test
rows, and a 1,152,998,343-byte download. Its published schema contains source
and feedback answer text, `proof_repair`, final `lean_code`, validity, token and
tactic counts, and model score/rank.

It does not publish attempt identifiers or parent lineage, Lean or Mathlib
revision, native checkpoint identity, per-attempt verdict accounting, or
verifier CPU. Feedback and prior attempts may be embedded inside free-form text,
but textual containment is not an executable exact-prefix match.

**Decision:** stop at schema inspection. A bulk download cannot answer the
value-gate question and would violate D-036's novel-information law.

## Trace-level attribution study

The paper *What Helps Agentic Lean Provers? A Trace-Level Attribution Study*
(OpenReview forum `ShhLinF41r`) describes a frozen 100-task Lean 4 benchmark and
raw JSONL logging of model responses, submissions, tool calls, compiler
messages, final verdicts, and timing. Such records could be unusually relevant
because iterative feedback may produce independent attempts sharing exact
prefixes.

The public release surface does not currently expose those records. The ICML
virtual page links only to OpenReview. Stella Biderman's official publication
page lists only a paper link for this work, while it labels code and artifacts
separately for releases that provide them. Public repository and Hugging Face
searches for the title and authors found no trace corpus. The paper describes a
valuable artifact, but that description is not an accessible dataset.

**Decision:** record this as the strongest unavailable lead. Do not infer
prefix reuse or timing from paper aggregates, and do not reproduce its runs.
If the authors expose the already-generated raw JSONL, freeze its revision and
inspect the schema before reading the corpus.

## Result

Neither candidate reopens implementation. FormalMath is available but missing
decision-critical fields; the attribution study describes the right class of
trace but does not expose it. The next meaningful input is an already-existing
artifact, not more SHRED seeds or a newly generated benchmark.
