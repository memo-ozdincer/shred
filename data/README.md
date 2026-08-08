# External Data

`c0.manifest.json` identifies the immutable discovery inputs. The complete
proposal records are committed as four deterministic gzip shards in `c0/proofs`.
The manifest records hashes for both the compressed repository files and their
original uncompressed JSONL content.

Run:

```bash
lean-prefix audit --manifest data/c0.manifest.json
```

No sibling checkout or extraction is required. `--source-root` remains
available for auditing a relocated copy.
