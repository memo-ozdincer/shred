# SHRED RL arithmetic-closure benchmark

## What the dataset is

The SHRED RL arithmetic-closure workload is a frozen slice of an authentic
GRPO training verifier stream, not a synthetic proof benchmark and not a
collection selected from cached execution.

Its source is the completed C1 GRPO-default run in the sibling RL repository:

```text
run:       c1-grpo-default-full-20260814-seed42-5ced4c3
condition: c1_grpo_default
run Git:   5ced4c3210381950d51048355fcbd95f50a6004a
source:    runs/c1-grpo-default-full-20260814-seed42-5ced4c3/
           artifacts/proofs/global_step_604.jsonl
SHA-256:   1db715569b8d1d8d7abf558bfd0c0c9b59779fd2ae7e959af0a31f0bb622d9f0
```

The full C1 stream contains 308,960 registered Lean proof proposals for 9,655
training theorems, with 32 proposals per theorem. It was produced during a
complete 604-step GRPO run starting from the pinned
DeepSeek-Prover-V1.5-SFT revision
`e9a6e6fbb67620d4e9c4944bc51ff7c435af12da`. The stream records the proposals
that the RL system actually sent to its Lean verifier to obtain binary rewards.
The external source remains read-only and is registered by
`data/c1-rl.manifest.json` rather than copied into Git.

The benchmark workload contains exactly 505 of those theorem groups and the
first 32 C1 proposals for each group in physical generation order: **16,160
proposals total**. The theorem-list digest is
`7a98690fd3ad2349d9f255b0fd27262265bb50b40fa133be172dddb910233628`,
computed over sorted theorem names with one trailing newline per name. The
selection command emits the full names and per-theorem admission evidence.

C1's historical verifier labels mark 15,774 of the 16,160 proposals correct
(97.61%), with three timeouts and four proof-parse failures. These counts
describe the frozen stream; the SHRED evaluation must still re-run every
proposal under ordinary Lean and use those current verdicts as authoritative.

## How the 505 theorems were chosen

Admission uses only C0's earlier independent-execution telemetry. It does not
read C1 outcomes, SHRED cache events, D030 cached timings, or projected
speedups. A C0 theorem is admitted exactly when:

1. all 32 registered proposals have unchanged full-verification process CPU;
2. their total independent verification costs at least 4 CPU-seconds;
3. at least four successful proposals repeat an exact final tactic edge of
   Lean kind `nlinarith`, `linarith`, or
   `Mathlib.Tactic.Positivity.positivity`;
4. for each repeated edge, conservative reusable cost is
   `sum(reached CPU) - max(reached CPU)`; and
5. those conservative repeated costs total at least 40% of all 32 proposals'
   full-verification CPU.

This rule yields 505 of 9,655 C0 theorems. Their C0 proposals consumed
8,223.101 CPU-seconds. Conservative repeated expensive-closer cost was
4,073.644 seconds, or **49.539%** of total verification CPU. This is an
admission signal, not a speed measurement.

The companion control is 128 non-admitted C0 theorems selected by the fixed
SHA-256 seed `shred-rl-arithmetic-closure-control-v1`. Its C1 slice contains
4,096 proposals; its theorem-list digest is
`928f2feebbc51329673feffbf425515550225903e019c2e167833db7372f001b`.
The control is reported separately and cannot dilute or improve the admitted
workload's result.

## Why this is an RL workload

Group-based theorem-proving RL samples many candidate proofs for each training
theorem, verifies every candidate, and uses the resulting Lean verdicts as
rewards. The same curriculum is revisited across optimization steps and runs.
For an easy arithmetic theorem, many candidates can independently rediscover
the same expensive `nlinarith`, `linarith`, or `positivity` closure. The RL
learner still needs all 32 attributable rewards, but the verifier need not
regenerate an identical checked certificate every time.

This cohort captures precisely that operational regime:

- it consists of actual training-time verifier requests, not benchmark-only
  inference;
- the proposal budget is the real 32-sample RL group size;
- admission is learned from a prior rollout, as an online system could do;
- evaluation uses a later GRPO verifier stream, after policy optimization has
  changed the proposal distribution;
- incorrect proofs, parsing failures, timeouts, misses, and unsupported syntax
  remain part of the cost and accounting; and
- the high C1 correctness rate reflects reward-saturated arithmetic groups
  where RL continues paying for many independently verified positive samples.

The claim is deliberately conditional: SHRED targets RL batches that a
read-only prior-iteration profile identifies as expensive-closure dominated.
It is not a claim about arbitrary Lean corpora.

## What the existing evidence bounds

**Upper-sensitivity hypothesis:** applying the slower 27.05x
successful-transfer anchor and 2% total overhead while retaining all of the
cohort's 49.539% C0 reuse signal gives **45.7% less CPU**, or **1.84x
CPU-equivalent throughput**.

The 49.539% input is itself an upper bound derived from repeated exact final
edges, not an executable certificate hit rate. Exact automatic-key
compatibility, first captures, misses, and policy distribution shift reduce the
realized fraction. The 1.84x value is therefore not a conservative forecast and
is not headline-ready.

## No-compute theory gate

No C1 Lean extraction, replay, paired execution, or cluster job is authorized.
Existing artifacts must first establish a CPU-weighted conservative retention
bound. At the 27.05x transfer ratio and 2% overhead:

- 1.5x overall requires 36.690% realized reusable CPU;
- this equals 74.062% retention of the 49.539% admission signal; and
- failure to establish that lower bound stops the planned run.

The analysis must use exact automatic-key events already recorded in D030,
charge the first capture in every key group, include misses and rejected
applications, and preserve disagreement/fallback accounting. Tactic heads,
proof text similarity, and the admitted exact-edge count are descriptive only.
Selected fast pairs cannot establish the bound.

Only after this gate passes may a new decision authorize a bounded C1 run. That
decision must state the expected CPU cost, expected saved CPU, stopping rule,
and why the expected information or system value justifies the compute.

## Eventual headline promotion gate

The number becomes headline-grade only after one registered paired run meets
all of the following:

- the C1 source manifest and 505-theorem selection digest match exactly;
- all 16,160 proposals receive one attributable baseline and SHRED verdict;
- ordinary Lean acceptance agrees for every proposal;
- cached, captured, missed, rejected, uncacheable, failed, timed-out, and reset
  proposals are all counted;
- baseline and SHRED use identical ordered inputs, environment, timeouts,
  concurrency, and hardware;
- CPU, wall time, throughput, peak memory, median, p90, p95, p99, and
  per-theorem results are reported; and
- the 128-theorem control is reported alongside the admitted cohort.

Before the theory gate and paired run, acceptable wording is limited to:

> A frozen 16,160-proposal RL arithmetic-closure workload has a 49.5%
> prior-iteration repeated-cost upper bound; existing-artifact analysis is
> testing whether enough survives exact certificate matching to justify a run.

After a passing run, the headline must use the actual result:

> On a held-out 16,160-proposal GRPO verifier workload, SHRED reduced Lean
> verification CPU by X% and delivered Yx CPU-equivalent throughput with
> 16,160/16,160 ordinary-Lean verdict agreement.

## Reproduction

```bash
PYTHONPATH=src python -m lean_prefix audit --manifest data/c1-rl.manifest.json
PYTHONPATH=src python -m lean_prefix.rl_workload
PYTHONPATH=src python -m lean_prefix.rl_workload --summary
```

The selection reads the immutable D019 artifact manifest and verifies all 128
C0 replay artifact hashes before emitting the full cohort and control.
