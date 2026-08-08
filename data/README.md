# External Data

`c0.manifest.json` identifies the immutable discovery inputs. It contains paths
and hashes, not the proof records themselves.

Run:

```bash
lean-prefix audit --manifest data/c0.manifest.json
```

Use `--source-root` when the sibling project is mounted elsewhere.

