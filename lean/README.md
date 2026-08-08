# Pinned Lean Component

The extractor uses the exact Lean and Mathlib revisions from the C0 verifier:

- Lean: `leanprover/lean4:v4.9.0-rc1`
- Mathlib fork: `xinhjBrant/mathlib4`
- Mathlib commit: `2f65ba7f1a9144b20c8e7358513548e317d26de1`

For local development with the existing C0 workspace:

```bash
cd /scratch/memoozd/rl/DeepSeek-Prover-V1.5/mathlib4
lake env lean --run /scratch/memoozd/rl/lean-prefix/lean/LeanPrefix/Extract.lean
```

The executable consumes JSON Lines on standard input and emits one JSON object
per input. It parses with Lean's registered `tacticSeq` parser after importing
the pinned Mathlib environment. It does not elaborate or execute tactics.

