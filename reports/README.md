# Reproducible Reports

Checked-in reports contain aggregate, non-secret results produced by a documented
command. Raw proof data and private traces belong under `reports/private/`, which
is Git-ignored.

`c0_audit.json` is reproduced with:

```bash
lean-prefix audit \
  --manifest data/c0.manifest.json \
  --output reports/c0_audit.json
```

`c0_exact_analysis.json` is reproduced with:

```bash
lean-prefix analyze-exact \
  --manifest data/c0.manifest.json \
  --output reports/c0_exact_analysis.json
```

`c0_native_prefix.json` and its ignored proposal-level artifact are reproduced
inside the pinned C0 Mathlib workspace with:

```bash
lean-prefix analyze-native \
  --manifest data/c0.manifest.json \
  --lean-workspace /path/to/pinned/mathlib4 \
  --extractor lean/LeanPrefix/Extract.lean \
  --artifact artifacts/c0_native_units.jsonl.gz \
  --output reports/c0_native_prefix.json
```

The aggregate report records all relevant revisions and the artifact checksum.
The ignored artifact can then reproduce the deterministic review sample:

```bash
lean-prefix select-review \
  --manifest data/c0.manifest.json \
  --artifact artifacts/c0_native_units.jsonl.gz \
  --output reports/c0_review_sample.json
```

The final automatic closing-certificate prevalence evidence is checked in as
`c0_certificate_prevalence_d030.json`; its hand audit is
`c0_certificate_prevalence_review.md`. The representative stratum is complete
and verdict-preserving, and its 3.2405% CPU saving fails the frozen 15% gate.
The enriched stratum is explicitly incomplete and diagnostic only.

The compute-free RL cohort retention decision is checked in as
`c0_rl_retention_gate.json`; its audit is `c0_rl_retention_gate_review.md`.
It is reproduced from already-existing D019 and D030 artifacts with:

```bash
PYTHONPATH=src python -m lean_prefix.retention_gate
```

The report records 13.892% paired CPU saving (1.161x) on 864 overlap proposals,
with 864/864 verdict agreement and a 7.759%--20.258% theorem-bootstrap interval.
It decisively fails the 36.690% reduction required before any C1 compute.
