# Data and Provenance

## Discovery corpus

The discovery corpus is the completed C0 rollout from the sibling project at:

```text
/scratch/memoozd/rl/restriction
```

Authoritative project commit: `41aab85` on `dominant-mode-blocking`.

Authoritative aggregate records:

```text
runs/c0-base-20260804-seed42-complete/validation.json
runs/c0-base-20260804-seed42-complete/metrics.json
research/COMPUTE_SESSION_HANDOFF.md
```

The repository is self-contained: four deterministic gzip shards under
`../data/c0/proofs/` contain all 308,992 physical proposal records. The
machine-readable source list, compressed hashes, and original uncompressed
source hashes are in `../data/c0.manifest.json`.

## Data policy

- The sibling project is provenance-only and read-only from this repository.
- Only the four reviewed C0 gzip shards are tracked. Unmanaged JSONL, Parquet,
  extracted data, caches, and private traces remain Git-ignored.
- Analyses identify source files by SHA-256, not only by mutable paths.
- Derived reports contain aggregate data or explicitly reviewed examples.
- Any public release requires a separate review of licenses, privacy, model
  terms, theorem provenance, and whether generated proofs should be published.
- The private GitHub repository and the source project's independent archive
  provide copies beyond cluster scratch.

## Registered selection

There are 308,992 physically generated and verified records. The registered
scientific sample retains the first 32 proposals for each of 9,655 theorems.
One dataloader-padding group of 32 additional proposals is separately accounted
for and excluded, producing 308,960 registered proposals.
