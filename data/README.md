# External Data

`c0.manifest.json` identifies the immutable discovery inputs. The complete
proposal records are committed as four deterministic gzip shards in `c0/proofs`.
The manifest records hashes for both the compressed repository files and their
original uncompressed JSONL content.

Run:

```bash
shred audit --manifest data/c0.manifest.json
```

Register another JSONL or JSONL.gz corpus with:

```bash
shred init --input /path/to/rollouts.jsonl.gz \
  --samples-per-theorem 32 --output workload.manifest.json
```

`c1-rl.manifest.json` registers the read-only, held-out C1 GRPO verifier stream
in the sibling RL repository. It does not copy or rewrite the 476 MiB source
JSONL. See `../docs/RL_BENCHMARK.md` for the exact 505-theorem evaluation
cohort and its prior-iteration admission rule.

Each record must contain `theorem_name`, `proof`, and `correct`. The initializer
stores paths, compressed and logical-content SHA-256 values, proposal counts,
and explicit padding accounting; it never modifies the source files.

No sibling checkout or extraction is required. `--source-root` remains
available for auditing a relocated copy.
