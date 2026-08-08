#!/usr/bin/env bash
set -euo pipefail

: "${LEAN_WORKSPACE:?set LEAN_WORKSPACE to the pinned C0 mathlib4 workspace}"

shard_count="${LEAN_PREFIX_SHARD_COUNT:-1}"
shard_index="${LEAN_PREFIX_SHARD_INDEX:-${SLURM_ARRAY_TASK_ID:-0}}"
restart_every="${LEAN_PREFIX_RESTART_EVERY:-128}"
memory_gib="${LEAN_PREFIX_MEMORY_GIB:-24}"
timeout_seconds="${LEAN_PREFIX_TIMEOUT_SECONDS:-300}"
cli="${LEAN_PREFIX_CLI:-python -m lean_prefix}"

mkdir -p artifacts/replay reports/private/replay

# Word splitting is intentional for LEAN_PREFIX_CLI so it can be either the
# installed console script or `python -m lean_prefix`.
# shellcheck disable=SC2086
$cli profile-replay \
  --manifest data/c0.manifest.json \
  --native-artifact artifacts/c0_native_units.jsonl.gz \
  --lean-workspace "$LEAN_WORKSPACE" \
  --artifact "artifacts/replay/shard-${shard_index}-of-${shard_count}.jsonl.gz" \
  --output "reports/private/replay/shard-${shard_index}-of-${shard_count}.json" \
  --shard-count "$shard_count" \
  --shard-index "$shard_index" \
  --restart-every "$restart_every" \
  --timeout-seconds "$timeout_seconds" \
  --memory-limit-gib "$memory_gib"
