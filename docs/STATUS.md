# Project Status

Last updated: 2026-08-09

## Established

- The private repository is self-contained: all four audited C0 corpus shards
  are checked in.
- The frozen corpus contains 9,655 theorems, 308,960 registered proposals,
  168,029 Lean-correct proposals, and 32 separately excluded padding records.
- Phase 1 measured 42,815 exact duplicate occurrences, 304,546 conservatively
  parseable proposals, 888,421 tactic occurrences, and 689,193 exact trie
  nodes. The 199,228 repeated occurrences are syntax evidence, not a speedup.
- The source manifest, proposal identities, hashes, native tactic boundaries,
  deterministic review sample, and 15% reached-prefix CPU gate are frozen.
- Complete-proof verification matches C0's exact fenced-code parsing and Lean
  remains the sole correctness authority.

## Phase 2 correction

The first full 128-shard diagnostic covered all 308,960 proposals but cannot
support a cost claim. It exposed 36 C0 parsing mismatches, 72 reconstructed
step-replay mismatches, 35 process errors, 118 full timeouts, and 6 replay
timeouts. The 112-worker launch caused severe CPU contention, while memory
remained safe. D-012 records the C0 parsing fix.

D-013 rejects reconstructed or serialized proof-state replay as Phase 2 cost
evidence. Lean execution can depend on hidden elaborator and recursion context
that is absent from an apparently identical visible goal. Retrying a tactic
from such a state can therefore change both acceptance and cost.

D-014 defines the corrected measurement:

1. Run the unchanged complete declaration for the authoritative verdict and
   high-resolution process CPU.
2. Run the same declaration with Lean's in-process C profiler enabled.
3. Deterministically align profiler records to the frozen top-level tactic
   prefix and assign only conservative attributable cost.
4. Keep profiler overhead separate. Any unsupported or ambiguous case falls
   back to independent verification and contributes zero claimed opportunity.

The 19-proposal regression selected from every known discrepancy family passed:
19/19 unchanged full verdicts, 14/14 profile-eligible verdicts, 5 explicit
fallbacks, 32 reached units, and no errors or timeouts. It is a semantic
regression, not a representative performance sample.

## Diagnostic breadth gate

The deterministic six-shard D017 run completed all 14,496 proposals in 20.2
minutes. All full verdicts agree; all 12,758 profile-eligible verdicts agree;
1,508 fallbacks are explicit; 32,054 reached units have complete CPU telemetry;
and there are no timeout or process failures. The aggregate and hand review are
`reports/c0_replay_breadth_d017.json` and
`reports/c0_replay_breadth_d017_review.md`.

Its conservative opportunity estimate is 6.463%, with a theorem-bootstrap interval of
5.519%–7.501%. That is below the frozen 15% threshold, but these six shards are
an operational breadth set rather than the registered complete sample. It is a
strong warning, not the final gate decision. D017 started before the final rule
that rejects ambiguous duplicate profiler-frame alignments. That rule can only
remove opportunity, but it changes eligibility, so D017 is diagnostic rather
than the final breadth artifact.

## Next milestone

Commit the exact implementation, rerun the same six shards as
`replay_d018_breadth` from that clean commit, then launch the complete 128-shard
`replay_d019` census with 32 workers while allocation `19352896` remains. Only
the complete, representative 308,960-proposal report may decide the frozen 15%
gate.

If the gate passes, Phase 3 begins with a frozen warm independent-execution
baseline and then the smallest exact prefix-trie executor. If it fails, publish
the characterization and stop the version-one executor path; do not weaken
exactness or tune the threshold after seeing the answer.
