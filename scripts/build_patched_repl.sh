#!/usr/bin/env bash
set -euo pipefail

: "${REPL_SOURCE:?set REPL_SOURCE to the pinned upstream REPL checkout}"
: "${REPL_DESTINATION:?set REPL_DESTINATION to a new build directory}"

expected_commit="c6199a81de2a7e16cb27d6f85f56cff7043cd27f"
actual_commit="$(git -C "$REPL_SOURCE" rev-parse HEAD)"
if [[ "$actual_commit" != "$expected_commit" ]]; then
  echo "expected REPL commit $expected_commit, found $actual_commit" >&2
  exit 1
fi
if [[ -e "$REPL_DESTINATION" ]]; then
  echo "destination already exists: $REPL_DESTINATION" >&2
  exit 1
fi

mkdir -p "$REPL_DESTINATION"
cp -a \
  "$REPL_SOURCE/REPL" \
  "$REPL_SOURCE/REPL.lean" \
  "$REPL_SOURCE/lakefile.lean" \
  "$REPL_SOURCE/lean-toolchain" \
  "$REPL_DESTINATION/"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
patch -d "$REPL_DESTINATION" -p1 \
  < "$repo_root/patches/repl-proof-snapshot.patch"

grep -Fq 'declName : Option String := none' \
  "$REPL_DESTINATION/REPL/JSON.lean"
grep -Fq 'maxHeartbeats := 0' \
  "$REPL_DESTINATION/REPL/Main.lean"
grep -Fq '(ctx := p.termContext)' \
  "$REPL_DESTINATION/REPL/Snapshots.lean"
(cd "$REPL_DESTINATION" && lake build)

executable="$REPL_DESTINATION/.lake/build/bin/repl"
sha256sum "$executable"
