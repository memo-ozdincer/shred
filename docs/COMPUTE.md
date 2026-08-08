# Phase 2 Compute Runbook

The replay profiler is CPU- and RAM-bound; it does not use GPUs. Each worker
owns one persistent pinned Lean REPL and processes complete theorem blocks.
Outputs are written directly under the repository on scratch so they survive
the allocation. A node-local copy of the 3.9 GiB Mathlib workspace is optional
for faster startup, but it is never the sole output location.

## Recommended allocation

Prefer one 192-core, 6 TiB CPU node. Start with 128 workers, one logical core
per worker, a 24 GiB hard address-space limit per Lean process, a 300-second
request timeout, and restart each process after 128 proposals. This is below
3 TiB even at every hard limit and leaves substantial memory for filesystem
cache and transient peaks.

On a 748 GiB node, use 24 workers with the same per-process limit. Do not launch
128 workers there merely because the cores exist.

## Run

From a clean checkout with `artifacts/c0_native_units.jsonl.gz` restored to the
checksum in `reports/c0_native_prefix.json`:

```bash
export LEAN_WORKSPACE=/path/to/pinned/mathlib4
export LEAN_PREFIX_SHARD_COUNT=128
export LEAN_PREFIX_CLI=.venv/bin/lean-prefix

seq 0 127 | xargs -P 128 -I '{}' env LEAN_PREFIX_SHARD_INDEX='{}' \
  scripts/profile_replay_shard.sh
```

Every shard scans the small compressed manifests but executes only theorems
whose stable corpus ordinal belongs to that shard. A failed shard can be rerun
without touching completed shards.

## Consolidate and gate

After all shards finish, pass every artifact to the summarizer and require all
308,960 proposal IDs:

```bash
args=()
for path in artifacts/replay/shard-*.jsonl.gz; do
  args+=(--artifact "$path")
done
.venv/bin/lean-prefix summarize-replay "${args[@]}" \
  --expected-proposals 308960 \
  --gate-fraction 0.15 \
  --output reports/c0_replay_cost_summary.json
```

The summarizer refuses duplicate proposal IDs, refuses a cost claim on any
verdict disagreement, labels missing mappings/replays as incomplete, and uses
a fixed theorem-bootstrap seed. Preserve all shard artifacts until the final
report, hashes, and backup have been verified.

## Expected scale

The login-node integration run is not a throughput benchmark. A planning range
for 128 workers is roughly 8–20 wall-clock hours, dominated by authentic tactic
cost and 300-second tails. Use observed progress from the first 30 minutes to
revise the ETA; do not extrapolate from syntax extraction, which is orders of
magnitude cheaper.
