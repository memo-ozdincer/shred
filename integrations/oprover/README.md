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
4. preserve all non-SHRED stderr verbatim;
5. carries native tactics and CPU records through OProver's existing verifier
   result, with explicit fallback when either is missing.

The remaining integration work is to group only the existing
`r{round}_p{prompt}_s{rollout}` siblings, lease their capture REPL until exact
comparison, pickle one representative checkpoint, freeze environment/context
receipts, and export every attempt through `seal-authentic-trace`.

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
