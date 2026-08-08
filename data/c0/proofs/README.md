# C0 Proof Shards

These four deterministic gzip files contain the complete physical C0 rollout:
308,992 generated and Lean-verified proposal records. Registration retains the
first 32 proposals for each of 9,655 theorems and separately excludes one
32-proposal dataloader-padding group, yielding 308,960 scientific proposals.

The files were produced with `gzip -n -9`, so their bytes do not depend on the
source filename or modification time. `../c0.manifest.json` records both the
gzip SHA-256 and the SHA-256 of the decompressed original JSONL.

The data is presently stored only in the private repository. Review licensing,
model terms, and release intent before changing repository visibility.

