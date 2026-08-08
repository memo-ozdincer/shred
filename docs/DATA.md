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

The machine-readable source list and immutable checksums are in
`../data/c0.manifest.json`.

## Data policy

- The sibling project is read-only from this repository.
- Raw JSONL and Parquet data remain external and Git-ignored.
- Analyses identify source files by SHA-256, not only by mutable paths.
- Derived reports contain aggregate data or explicitly reviewed examples.
- Any public release requires a separate review of licenses, privacy, model
  terms, theorem provenance, and whether generated proofs should be published.
- Cluster scratch is not the only archival copy of the C0 corpus; the source
  project records its independent backup.

## Registered selection

There are 308,992 physically generated and verified records. The registered
scientific sample retains the first 32 proposals for each of 9,655 theorems.
One dataloader-padding group of 32 additional proposals is separately accounted
for and excluded, producing 308,960 registered proposals.

