# Verification Strategy

## Layer 1 — Corpus and accounting

- Source checksums match the frozen manifest.
- Registered and physical proposal counts are distinct and exact.
- Padding selection is deterministic and reproduced.
- Every proposal retains a stable source identity.

## Layer 2 — Parser and trie

- Lean-native units reconstruct the original proof without semantic rewriting.
- Comments, whitespace, nested `by`, bullets, combinators, and malformed outputs
  have explicit tested behavior.
- Trie node counts match hand-constructed synthetic examples.
- Input ordering does not change the set of unique nodes or proposal verdicts.

## Layer 3 — State isolation

- Sibling branches cannot observe each other's metavariable assignments.
- Failure, exception, timeout, and cancellation do not corrupt the parent.
- Repeated execution of cacheable prefixes yields equivalent states.
- Effectful or nondeterministic operations are detected or fall back.

Before the executor exists, the cost profiler must additionally prove:

- complete-proof verdicts agree with frozen C0 labels;
- enabling the in-process profiler does not change the complete-proof verdict;
- profiler records align to a deterministic prefix of frozen Lean-native units;
- missing/ambiguous alignment, structural controls, parsing failures, errors,
  and timeouts use explicit independent fallback and create no savings;
- rejected-proof suffixes after the first failed unit are labeled unreachable,
  not zero-cost;
- invalid-root tactic units are labeled `unreachable_invalid_root`, contribute
  zero reached-prefix work, and retain full verification cost in the denominator;
- full-request failures and 300-second timeouts remain attributable to proposals;
- profiler overhead is reported separately from the baseline and opportunity;
- shard consolidation rejects duplicate or missing proposal IDs.

## Layer 4 — Verdict equivalence

- Independently check every comparison input with the frozen reference runner.
- Compare accept, reject, error, and timeout under the registered policy.
- Treat any unexpected acceptance disagreement as a release blocker.
- Preserve and hand-inspect every disagreement artifact.

## Layer 5 — Performance

- Warm both systems before timing.
- Use identical hardware, concurrency, inputs, ordering, and limits.
- Run enough repetitions to characterize variance.
- Record CPU time as well as wall time so parallelism is not mistaken for work
  elimination.
- Include parsing, trie construction, state copying, serialization, fallback,
  and final checking in end-to-end results.

## Hand-reading protocol

At each analysis milestone, inspect examples selected before viewing their
contents from these strata:

- correct and incorrect;
- exact duplicate and unique;
- zero-, one-, two-, and deep-shared-prefix;
- shortest and longest proof deciles;
- cheapest and most expensive measured tactic deciles;
- parser fallback and malformed outputs;
- timeout and high-memory cases;
- theorems near median and tail reuse.

Save identifiers, selection seed, reviewer notes, and any classification change.
