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
