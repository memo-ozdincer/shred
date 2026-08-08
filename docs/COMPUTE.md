# Phase 2 Compute Runbook

The replay profiler is CPU- and RAM-bound; it does not use GPUs. Each worker
owns one persistent pinned Lean REPL and processes complete theorem blocks.
Outputs are written directly under the repository on scratch so they survive
the allocation. A node-local copy of the 3.9 GiB Mathlib workspace is optional
for faster startup, but it is never the sole output location.

## Recommended allocation

A standard Nibi CPU node provides 192 logical CPUs and 748 GiB allocatable RAM
(`766000M`). Use 112 workers initially, one persistent REPL per worker, a 24
GiB hard address-space limit per REPL, a 300-second request timeout, and restart
each process after 128 proposals.

The 24 GiB value is a limit, not reserved memory. The largest RSS observed in
the integration checks was 3.71 GiB, so 112 workers project to about 416 GiB at
that observed peak and leave over 300 GiB for heavier cases, Python processes,
the OS, and filesystem cache. Check aggregate memory after 30 and 60 minutes.
Reduce concurrency if available RAM falls below 100 GiB or if the kernel/Slurm
reports memory pressure. A 6 TiB node is convenient but not required.

## Run

From a clean checkout with `artifacts/c0_native_units.jsonl.gz` restored to the
checksum in `reports/c0_native_prefix.json`:

```bash
export LEAN_WORKSPACE=/path/to/pinned/mathlib4
export LEAN_PREFIX_SHARD_COUNT=128
export LEAN_PREFIX_CLI=.venv/bin/lean-prefix
export PATH=/scratch/memoozd/.elan/bin:$PATH

seq 0 127 | xargs -P 112 -I '{}' env LEAN_PREFIX_SHARD_INDEX='{}' \
  scripts/profile_replay_shard.sh
```

Every shard scans the small compressed manifests but executes only theorems
whose stable corpus ordinal belongs to that shard. Each shard writes directly
to scratch. Its gzip artifact is durable once the corresponding JSON report is
written; a gzip interrupted before that point is incomplete and should be
overwritten by rerunning that shard.

To resume without overwriting completed shards:

```bash
for index in $(seq 0 127); do
  report="reports/private/replay/shard-${index}-of-128.json"
  test -s "$report" || echo "$index"
done | xargs -P 112 -I '{}' env LEAN_PREFIX_SHARD_INDEX='{}' \
  scripts/profile_replay_shard.sh
```

Run the worker command in a persistent terminal such as `tmux`. The allocation
ending kills active workers, but completed artifacts remain on `/scratch`.

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
for 112 workers is roughly 9–23 wall-clock hours, dominated by authentic tactic
cost and 300-second tails. Use completed-shard progress and aggregate CPU after
the first 30 and 60 minutes to revise the ETA; do not extrapolate from syntax
extraction, which is orders of magnitude cheaper.

## Operational checks

From the login node, verify that the allocation still belongs to this run:

```bash
squeue -j "$SLURM_JOB_ID" -o '%.18i %.24j %.2t %.10M %.10l %.4C %.10m %R'
```

On the compute node, monitor worker and node memory without changing the run:

```bash
free -h
pgrep -af '/REPL/.lake/build/bin/repl' | wc -l
ps -C repl -o rss= | awk '{sum += $1; if ($1 > max) max = $1} END {printf "rss_total_gib=%.1f rss_max_gib=%.1f\n", sum/1048576, max/1048576}'
```

Do not interpret a single theorem, startup interval, or partially completed
set of fast shards as the gate result.
