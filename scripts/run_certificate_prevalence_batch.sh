#!/usr/bin/env bash
set -euo pipefail

: "${LEAN_WORKSPACE:?set LEAN_WORKSPACE to the pinned C0 mathlib4 workspace}"
: "${LEAN_PREFIX_REPL_EXECUTABLE:?set the pinned patched REPL executable}"

parallelism="${LEAN_PREFIX_PARALLELISM:-64}"
memory_gib="${LEAN_PREFIX_MEMORY_GIB:-32}"
timeout_seconds="${LEAN_PREFIX_TIMEOUT_SECONDS:-300}"
run_name="${LEAN_PREFIX_RUN_NAME:-certificate_d026}"
selection="${LEAN_PREFIX_SELECTION:-reports/c0_certificate_prevalence_selection.json}"
inputs="${LEAN_PREFIX_INPUTS:-artifacts/certificate_d026_inputs.jsonl.gz}"

if [[ ! "$run_name" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "LEAN_PREFIX_RUN_NAME must be a simple path component" >&2
  exit 2
fi
if [[ ! "$parallelism" =~ ^[1-9][0-9]*$ ]]; then
  echo "LEAN_PREFIX_PARALLELISM must be a positive integer" >&2
  exit 2
fi

artifact_dir="artifacts/${run_name}"
report_dir="reports/private/${run_name}"
build_dir="/tmp/lean-prefix-${run_name}-${SLURM_JOB_ID:-local}"
mkdir -p "$artifact_dir" "$report_dir" "$build_dir/LeanPrefix"

lake env lean \
  --root="$PWD/lean" \
  -o "$build_dir/LeanPrefix/AutomaticCertificate.olean" \
  "$PWD/lean/LeanPrefix/AutomaticCertificate.lean"

export LEAN_PATH="$build_dir:${LEAN_PATH:-}"
export LEAN_WORKSPACE LEAN_PREFIX_REPL_EXECUTABLE
export LEAN_PREFIX_INPUTS="$inputs"
export LEAN_PREFIX_ARTIFACT_DIR="$artifact_dir"
export LEAN_PREFIX_REPORT_DIR="$report_dir"
export LEAN_PREFIX_MEMORY_GIB="$memory_gib"
export LEAN_PREFIX_TIMEOUT_SECONDS="$timeout_seconds"

run_one() {
  local theorem="$1"
  if [[ ! "$theorem" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "unsafe theorem name: $theorem" >&2
    return 2
  fi
  .venv/bin/lean-prefix run-certificate-prevalence-theorem \
    --input-artifact "$LEAN_PREFIX_INPUTS" \
    --theorem "$theorem" \
    --lean-workspace "$LEAN_WORKSPACE" \
    --repl-executable "$LEAN_PREFIX_REPL_EXECUTABLE" \
    --timeout-seconds "$LEAN_PREFIX_TIMEOUT_SECONDS" \
    --memory-limit-gib "$LEAN_PREFIX_MEMORY_GIB" \
    --artifact "$LEAN_PREFIX_ARTIFACT_DIR/${theorem}.jsonl.gz" \
    --output "$LEAN_PREFIX_REPORT_DIR/${theorem}.json" \
    > "$LEAN_PREFIX_REPORT_DIR/${theorem}.stdout"
}
export -f run_one

jq -r '.representative[].theorem_name, .enriched[].theorem_name' "$selection" |
  xargs -r -n 1 -P "$parallelism" bash -c 'run_one "$1"' _
