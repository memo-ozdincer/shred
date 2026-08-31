# Authentic branch-trace gate review

Date: 2026-08-31

Evidence label: **Observed** source and artifact audit. This is not a measured
performance result.

## Question

Can an already-published authentic Lean search, tactic-RL, or repair artifact
support the D-034 gate without generating proposals or running Lean?

The minimum useful artifact must preserve:

- exact theorem and environment identity;
- at least eight unchanged continuations from one Lean-native checkpoint;
- every continuation and attributable Lean verdict, not only the winning path;
- per-continuation verifier CPU cost and common-prefix verifier CPU cost;
- enough checkpoint groups for aggregate, median, tail, and per-theorem results;
- pipeline timing sufficient to distinguish verifier speedup from end-to-end
  training or search speedup.

Pretty-printed goals, tactic-head matches, completed proof trees, and whole-run
wall time do not substitute for those fields.

## Pinned audit

The repositories and exact revisions are frozen in
`data/authentic-branch-source-manifest.json`. They were cloned only under the
ignored `external-data/` directory. No model generation, Lean execution, or
cluster work was performed.

| Source | What the code preserves | Why the available repository artifact does not pass |
| --- | --- | --- |
| BFS-Prover-V2 | Best-first search samples 16 tactics and applies them from retained LeanDojo nodes. It records aggregate tactic, model, and total time; the returned proof statistics cover the selected proof path. | The pinned repository contains code and benchmark machinery, not completed full-tree result shards. `SearchResult` does not serialize every attempted branch with its parent checkpoint and successful per-edge CPU cost. Ordinary same-node fan-out is already part of the prover, so SHRED cannot claim that as a new cross-attempt optimization. |
| nanoproof | MCTS nodes retain `LeanProofBranch` objects. Saved theorem attempts can contain parent identifiers, actions, states, and full/simplified trees; generated tactics are also saved by a live run. | No completed run shards are committed at the pinned revision. Serialized nodes omit live checkpoint objects and per-edge verifier timing. Existing code already applies several actions to the same retained branch, so a future trace would characterize its native tree execution rather than prove a new same-process fan-out mechanism. |
| LeanTree | Lean-native proof structure and a checkpoint-capable server implementation. | Dataset generation describes completed source proofs, not authentic alternative continuations sampled from one search checkpoint. It does not provide the branch population and verifier-cost fields required by D-034. |
| LeanProgress | Utilities refer to collected BFS trajectories and build progress-prediction datasets. | The referenced combined state JSONL is not committed at the pinned revision. The preprocessing is aimed at successful trajectories/progress labels, not complete sibling branches with per-edge verifier cost. |
| Lean-Prover | Repair sessions emit timestamped JSONL events and preserve successive whole-file revisions and final run duration. | No user session corpus is committed. Events time the overall repair process but do not preserve Lean-native checkpoint lineage or isolate common-prefix and suffix verifier CPU. Revisions are therefore useful repair provenance, not an executable-prefix trace. |

## Result

**Observed:** zero of the five pinned public source repositories supplies an
already-completed artifact that contains all fields needed by D-034. The gate
cannot be evaluated from these sources without new data collection. This is a
missing-evidence result, not evidence that authentic workloads lack useful
branching.

**Observed:** the two clearest current tactic-search candidates, BFS-Prover-V2
and nanoproof, already retain a live state and fan several tactics out from that
state. The D-033 controlled 5.531x result validates the economics of that
standard architecture, but duplicating it inside a tree prover would not make
SHRED broadly novel or more useful.

## Consequence

No new Lean run is justified. In particular, do not manufacture a synthetic
corpus, rerun public benchmarks merely to add timings, or put the D-033 number
in the README as an authentic workload result.

The next potentially differentiating mechanism is exact reuse *outside* one
already-live tree: across independent attempts, workers, or policy iterations,
or a localized-repair protocol that intentionally branches unchanged suffixes
from a verified checkpoint. That direction is not authorized by this audit.
It first needs a correctness design for full hidden-context identity and
ordinary-Lean fallback; D-013's state-reconstruction failure means a serialized
pretty state is not sufficient.

A low-cost way to reopen the gate is an existing private run artifact from a
tree/RL prover that includes all sibling branches and per-edge verifier CPU, or
an existing repair log paired with Lean-native tactic-boundary telemetry. The
artifact may be inspected read-only under a frozen manifest. Instrumenting and
rerunning a prover remains a separate compute decision.
