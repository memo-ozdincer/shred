# Phase 2 Compute Runbook

The corrected profiler is CPU-bound and uses no GPU. Each worker owns one
persistent pinned Lean REPL. Every output is written directly to `/scratch`, so
completed reports survive the end of an allocation.

## Frozen execution settings

- 128 deterministic theorem shards;
- unchanged complete declaration as the authoritative baseline;
- separate in-process Lean C-profiler request for conservative attribution;
- 300-second timeout for either request;
- restart each REPL after 128 proposals;
- 48 GiB hard address-space limit per process;
- patched REPL executable SHA-256
  `89a35afd9f7a472b45e57dfd5dd0cede08bd0485ca4ac71b860d486cde8a42f3`.

The address-space value is a safety ceiling, not reserved RAM. Six-worker
monitoring on `c126` observed roughly 3.7–3.9 GiB RSS per active Lean process
and more than 730 GiB node memory available. The earlier 112-worker diagnostic
had safe memory but unacceptable CPU/cache contention and long timeout tails.
Use 24–32 workers for the complete run; do not return to 112 merely because RAM
is available.

## Final breadth gate

The deterministic breadth set is shards 7, 46, 53, 62, 78, and 93 (14,496
proposals total). Run it from the clean final-profiler commit under run name
`replay_d018_breadth_v2`. Its durable paths are:

```text
artifacts/replay_d018_breadth_v2/shard-INDEX-of-128.jsonl.gz
reports/private/replay_d018_breadth_v2/shard-INDEX-of-128.json
```

Consolidate only after all six reports exist:

```bash
args=()
for index in 7 46 53 62 78 93; do
  args+=(--artifact "artifacts/replay_d018_breadth_v2/shard-${index}-of-128.jsonl.gz")
done
.venv/bin/lean-prefix summarize-replay "${args[@]}" \
  --expected-proposals 14496 \
  --gate-fraction 0.15 \
  --output reports/private/replay_d018_breadth_v2_summary.json
```

This breadth result is a semantic and operational gate, not the registered
performance result. Require complete accounting, zero verifier disagreement,
zero profile-enabled verdict disagreement, and no missing CPU values.

## Complete census

From a clean committed checkout:

```bash
export PATH=/scratch/memoozd/.elan/bin:$PATH
export LEAN_WORKSPACE=/scratch/memoozd/rl/DeepSeek-Prover-V1.5/mathlib4
export LEAN_PREFIX_SHARD_COUNT=128
export LEAN_PREFIX_CLI=.venv/bin/lean-prefix
export LEAN_PREFIX_MEMORY_GIB=48
export LEAN_PREFIX_TIMEOUT_SECONDS=300
export LEAN_PREFIX_RESTART_EVERY=128
export LEAN_PREFIX_RUN_NAME=replay_d019
export LEAN_PREFIX_REPL_EXECUTABLE=/scratch/memoozd/rl/lean-prefix/artifacts/repl-patched-c6199a8-v2/.lake/build/bin/repl

seq 0 127 | xargs -P 32 -I '{}' env LEAN_PREFIX_SHARD_INDEX='{}' \
  scripts/profile_replay_shard.sh
```

To resume, select shards by missing report. A partial gzip without its report
is incomplete and may be overwritten; never overwrite a completed report
casually.

```bash
for index in $(seq 0 127); do
  report="reports/private/${LEAN_PREFIX_RUN_NAME}/shard-${index}-of-128.json"
  test -s "$report" || echo "$index"
done | xargs -P 32 -I '{}' env LEAN_PREFIX_SHARD_INDEX='{}' \
  scripts/profile_replay_shard.sh
```

Consolidate and require every registered proposal:

```bash
args=()
for path in artifacts/${LEAN_PREFIX_RUN_NAME}/shard-*.jsonl.gz; do
  args+=(--artifact "$path")
done
.venv/bin/lean-prefix summarize-replay "${args[@]}" \
  --expected-proposals 308960 \
  --gate-fraction 0.15 \
  --output reports/c0_replay_cost_summary.json
```

The summarizer fails closed on duplicate IDs or verdict disagreement and marks
missing full/step CPU or incomplete eligible profiling as incomplete. The 15%
threshold is frozen. Profiler-request CPU and wall time are overhead telemetry,
not part of the independent baseline denominator or claimed opportunity.

## Monitoring

Check progress and memory without changing the run:

```bash
squeue -j "$SLURM_JOB_ID" -o '%.18i %.24j %.2t %.10M %.10l %.4C %.10m %R'
free -h
ps -C repl -o rss= | awk '{sum += $1; if ($1 > max) max = $1} END {printf "rss_total_gib=%.1f rss_max_gib=%.1f\n", sum/1048576, max/1048576}'
find "reports/private/${LEAN_PREFIX_RUN_NAME}" -type f \
  -name 'shard-*-of-128.json' | wc -l
```

Reduce concurrency if available RAM falls below 100 GiB, the scheduler reports
memory pressure, or throughput degrades with rising timeout/process-error
counts. Do not change proof inputs, timeout, acceptance, or the scientific gate
to improve throughput.
