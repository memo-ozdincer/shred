# Design

## Core object: a rooted prefix trie

For version one, sharing is syntactic, rooted, and exact. A cache key contains:

```text
Lean toolchain hash
project/environment hash
imports and options hash
theorem statement/context hash
exact Lean-parsed tactic prefix
```

Candidates with different roots never share. Candidates that diverge never
merge again in version one, even if their displayed goals appear identical.

## Execution

1. Validate and parse all candidate proof bodies with Lean-native syntax.
2. Mark unsupported candidates for independent fallback.
3. Build a trie over eligible tactic units.
4. Initialize the theorem once.
5. Execute a node's tactic once against its parent state.
6. Preserve the resulting state for its children.
7. Attribute that node's result to every proposal passing through it.
8. Finish each leaf under ordinary Lean validation.
9. Return results in original proposal order.

## Failure behavior

- If a shared prefix fails deterministically, all descendants using that exact
  prefix receive the corresponding failure without executing impossible tails.
- If a tactic is effectful, nondeterministic, unsupported, or cannot be safely
  isolated, its proposals use independent execution.
- One branch's timeout or crash must not mutate sibling states.
- Cache lookup failure is a performance event, never a correctness event.

## Accounting

The engine distinguishes:

- logical proposals received;
- eligible and fallback proposals;
- independently executed tactic occurrences;
- unique prefix nodes executed;
- cache hits and misses;
- successful, failed, errored, and timed-out nodes;
- proposal verdicts and final validation outcomes.

Compute accounting uses the original proposal count, not the number of unique
nodes.

## Architecture boundaries

Initial components:

- corpus auditor;
- Lean-native proof-unit extractor;
- offline trie analyzer;
- independent replay profiler;
- reference verifier;
- prefix-trie executor;
- result comparator and report generator.

The profiler and reference verifier are reusable test oracles, not optional
development scaffolding.

