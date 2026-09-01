# OProver capture adapter

Status: the pinned Lean and REPL patches compile and the checked-in three-tactic
fixture passes the capture/control protocol validator. The complete OProver
stack has not been run, and no benchmark has been run.

These patches target the exact versions used by the audited OProver stack:

- Lean 4 `v4.15.0`, commit
  `11651562caae0a0b3973811508db2ab8903d3854`;
- `leanprover-community/repl` branch `v4.15.0`, commit
  `21966799da3691a0912b5a15193585bd2dd7165d`;
- OProver commit `b0cb2583b702d5040f84783ebba23d86241eac05`.

The Lean patch adds one option, `shred.cpuBoundaries`, and changes no tactic or
kernel behavior. A process launched with `LEAN_SHRED_CPU_BOUNDARIES=1` records
request parsing/elaboration scopes; the option additionally tags its tactic
scopes with exact ranges. Lean's existing RAII profiler emits tab-separated
records containing absolute process CPU plus completed-child CPU from
`getrusage`, an order number, nesting depth, and the tactic's exact source byte
range. Records bypass Lean's redirected diagnostic stream and go directly to
the process stderr descriptor, which is the stream Kimina retains. Windows
fails closed because this clock is not implemented there.

The REPL patch adds the original syntax kind and exact byte range to each
`allTactics` entry. `shred.oprover_adapter` joins only equal native byte ranges;
it never aligns proof text, pretty goals, or tactic heads. It forms the complete
request envelope from the first parser scope through the last elaboration scope,
which preserves injected option commands, and requires exactly one runtime
boundary per native tactic. Missing or ambiguous boundaries make the attempt a
fallback.

The OProver/Kimina patch now:

1. creates a distinct capture-enabled REPL pool, leaving ordinary REPLs
   untouched;
2. enables `shred.cpuBoundaries` and `allTactics` only for capture requests;
3. strips and retains SHRED lines before Kimina applies its existing stderr error
   policy;
4. preserves all non-SHRED stderr verbatim;
5. carries native tactics and CPU records through OProver's existing verifier
   result, with explicit fallback when either is missing;
6. groups only exact `r{round}_p{prompt}_s{rollout}` siblings whose formal
   statements are identical, and sends every unique complete attempt in one
   group request to one server;
7. leases one fresh capture REPL for the whole group, runs every unchanged body
   from environment `0`, and returns a group ID, position, size, and REPL UUID
   with every attributable result;
8. counts exact duplicate complete attempts as cached copies of one named
   representative; and
9. rejects mixed, missing, duplicate, or cross-REPL receipts as explicit
   fallbacks. Group transport requests are never silently retried because an
   uncertain retry could submit the same proposals twice.

The group protocol and its producer-side tests are checked in as source. All
three server-side group/checkpoint tests pass in a disposable minimal Python
environment built from the pinned source, in addition to static compilation
and exact patch round-trip validation. The full Verl training/verifier stack
is not installed, so its client-side test remains static-only. The same patch
now also selects a checkpoint only when at least eight unique
attempts share a nonempty exact native prefix with remaining suffix work. It
pickles a representative parent environment, root proof state, and first
divergent proof state into a server-owned directory; hashes those artifacts;
and hashes the ordered `(syntax kind, exact UTF-8 source bytes)` edges. Partial
or failed pickles are removed and every result receives an explicit checkpoint
fallback. The checked-in digest-only exporter now converts saved all-proof
records into the existing `seal-authentic-trace` input and fails the whole
export if any executed attempt lacks exact process CPU. No authentic value
screen is eligible until a normal independently useful run produces such an
artifact.

The exporter hashes each producer-owned rollout group plus fresh REPL UUID into
an `execution_scope_sha256`. This lets the screener separate opportunity inside
one live Kimina lease from an exact checkpoint identity recurring across
independent leases. Raw group and process identities do not enter the digest-
only trace.

Checkpoint artifact capture requires the server operator to configure
`LEAN_SERVER_SHRED_CAPTURE_DIR`. The directory is never supplied by a client,
artifact IDs contain only hashed group identity plus a fresh REPL UUID, leaf
directories use mode `0700`, and artifact files are changed to mode `0600`.

After a normal capture-enabled run has finished saving all-proof JSONL, export
without modifying those producer files:

```bash
shred export-oprover-trace \
  --input /path/to/all_proofs_stepN_roundR.jsonl \
  --output /new/path/oprover-shred-digests.jsonl \
  --expected-attempts PRODUCER_DECLARED_COUNT
```

Then pass that new digest-only partition and independently resolved workload
metadata to `shred seal-authentic-trace`. Both stages refuse overwrite and
reconcile the producer-declared count. Existing exact-complete-proof cache hits
remain explicit zero-cost fallbacks and never become SHRED opportunity.

This instrumentation is not a performance result. A future paired comparison
must use identical attempts and the same instrumented Lean build on both paths,
confirm agreement against the warm ordinary execution baseline, report the
instrumentation overhead separately, and satisfy D-040 before any headline.

After building the patched pins, the bounded validation command is:

```bash
PYTHONPATH=src python integrations/oprover/validate_capture.py \
  --lake /path/to/patched-lean/build/release/stage1/bin/lake \
  --repl /path/to/patched-repl/.lake/build/bin/repl \
  --project-dir /path/to/patched-repl
```

It runs one fixed three-tactic theorem with capture enabled and disabled. It
requires three exact byte-range-plus-syntax-kind matches, no telemetry inside
Lean diagnostic messages, empty unrelated stderr, and identical native tactic
output in the disabled control. It deliberately does not retain timing values
or make a performance claim.
