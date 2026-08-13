# Pinned Lean Component

## Use SHRED in a Lean project

Add the local SHRED Lean package to your `lakefile.toml`:

```toml
[[require]]
name = "shred"
path = "../shred/lean"
```

Then wrap only expensive closing tactics identified by a representative SHRED
profile:

```lean
import SHRED

open LeanPrefix.AutomaticCertificate

example (x : Real) (h : x = 3) : x ^ 2 = 9 := by
  reuse_closing in nlinarith
```

On a miss, `reuse_closing` runs the original tactic and captures its proof. On
an exact hit, it applies and type-checks that proof. Key construction or
application failure restores the tactic state and runs the original tactic.
Do not wrap every tactic indiscriminately; the representative study found that
broad automatic caching did not clear its end-to-end performance gate.

The research extractor uses the exact Lean and Mathlib revisions from the C0 verifier:

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

Phase 2 execution uses the separately pinned `xinhjBrant/repl` dependency in
the C0 Mathlib workspace. The repository's Python client connects through a
pseudo-terminal so the unmodified upstream process flushes each response and
does not truncate long JSON request lines.
