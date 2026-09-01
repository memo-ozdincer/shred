# Workload Profiler

SHRED starts with diagnosis because repeated proof text is not evidence of
meaningful compute savings. The profiler measures conservative, reached,
cost-weighted exact-prefix opportunity while preserving each proposal's
ordinary Lean verdict and full verification cost.

## Input schema

Input partitions are JSON Lines, optionally gzip-compressed. Every row needs:

```json
{"theorem_name": "example_1", "proof": "by\n  nlinarith", "correct": true}
```

Additional fields are preserved. `samples_per_theorem` is the registered
proposal budget; later rows for the same theorem are recorded as padding and
excluded from analysis without disappearing from physical accounting.

## Diagnose

```bash
shred init --input rollouts.jsonl.gz --samples-per-theorem 32 \
  --output workload.manifest.json

shred profile --manifest workload.manifest.json \
  --lean-workspace /path/to/mathlib4 --output-dir shred-profile
```

The output directory contains:

- `profile.json`: compact scope, metrics, artifact hashes, and recommendation;
- `reports/audit.json`: immutable input and accounting validation;
- `reports/exact.json`: whole-proof duplication statistics;
- `reports/native.json`: Lean-native parsing and exact-prefix counts;
- `reports/replay.json`: unchanged-verdict replay accounting;
- `reports/prefix-opportunity.json`: cost-weighted aggregate and uncertainty;
- `artifacts/`: deterministic native units and proposal-level replay records.

The default 256-proposal run is a screening tool. Use `--full` only for a
representative immutable corpus. `--native-artifact` skips extraction when a
compatible audited artifact already exists.

## Screen an existing RL or prover trace

If the producer already recorded exact Lean-native checkpoint lineage and
process CPU, use `shred screen-authentic-trace` instead of rerunning Lean. The
neutral JSONL contract, conservative cost equation, complete accounting rules,
and claim boundary are documented in `docs/AUTHENTIC_TRACE_CONTRACT.md`.

Use `shred seal-authentic-trace` first when the producer has JSONL telemetry but
not a SHRED manifest. It computes receipts and validates the export while
leaving producer files untouched. The expected attempt count is intentionally
producer-declared, so a truncated export cannot validate itself as complete.

This path never creates performance evidence by itself. Its output is an
Observed-input/Hypothesis projection that can stop a workload or justify
proposing one bounded paired implementation test.

## Decide, then integrate

A full profile recommends exact prefix work only when the conservative CPU
opportunity clears the configured gate. Below the gate, inspect expensive
closing-tactic tails rather than broadening matching rules. Certificate reuse
must remain exact and fail closed; see `lean/README.md` for integration.
