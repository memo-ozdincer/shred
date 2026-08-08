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

