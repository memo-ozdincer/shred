# SHRED

**Reuse repeated work across thousands of Lean proof attempts.**

SHRED is an installable Python package, Lean instrumentation suite, and
evidence-backed workload profiler. It tells you whether a proof workload has
enough cost-weighted repetition to justify caching before you modify a
verifier.

SHRED is a performance research system for batched Lean verification. It finds
computation shared by model-generated proof attempts, executes or generates
that work once, and preserves ordinary Lean as the final correctness authority.

On authentic proof closures from a large theorem-proving rollout, SHRED's
certificate-transfer prototype made repeated `nlinarith` closure up to
**325.6× faster** and repeated `positivity` closure **27.1× faster**, measured
as generation-plus-check versus application-plus-check. The project combines
Lean metaprogramming with a reproducible Python analysis and execution stack.

```text
32 independent proof attempts
            │
            ▼
  Lean-native parsing and telemetry
            │
       ┌────┴────┐
       ▼         ▼
 exact shared   checked closing
 prefixes       certificates
       └────┬────┘
            ▼
 ordinary Lean verdict for every proposal
```

## Why SHRED

Modern proof-generation systems can produce tens or hundreds of candidates for
the same theorem. Verification then treats every candidate as an unrelated
program-even when candidates repeat the same opening tactics or converge on
the same expensive closing calculation.

SHRED explores two conservative ways to remove that duplication:

1. **Exact prefix sharing.** Represent a batch as a tactic trie, execute a
   common rooted prefix once, and fork only when proofs diverge.
2. **Closing-certificate reuse.** Cache a proof produced by an expensive
   closing tactic, match it against an exact elaborated context and target,
   and ask ordinary Lean to type-check it before reuse.

Neither path weakens verification, invents tactics, or substitutes a learned
judge. Unsupported or unmatched attempts take the original execution path.

## Plug-and-play workflow

### 1. Diagnose your corpus

SHRED expects JSONL or JSONL.gz rollout records containing `theorem_name`,
`proof`, and `correct`. Register the files without copying or rewriting them:

```bash
shred init \
  --input /data/rollouts.jsonl.gz \
  --samples-per-theorem 32 \
  --output workload.manifest.json
```

Start with the bounded screening profile. It audits hashes and counts, extracts
Lean-native tactic boundaries, replays unchanged proofs, measures reached CPU
cost, and writes one recommendation:

```bash
shred profile \
  --manifest workload.manifest.json \
  --lean-workspace /path/to/mathlib4 \
  --output-dir shred-profile

cat shred-profile/profile.json
```

The default examines at most 256 proposals and always labels its recommendation
`screening_only`. If the signal is promising, repeat on a representative
immutable workload with `--full`. SHRED counts unsupported syntax, timeouts,
errors, and fallbacks instead of silently dropping them.

### 2. Act on the diagnosis

The report deliberately produces one of three full-workload decisions:

| Decision | Action |
|---|---|
| `prefix_reuse_candidate` | Benchmark an exact prefix executor against warm independent verification before deployment. |
| `do_not_deploy_exact_prefix_reuse` | Do not build prefix caching for this workload; inspect expensive closing-tactic tails. |
| `inconclusive` | Resolve attribution, timeout, fallback, or verdict-agreement failures first. |

### 3. Reuse expensive closing certificates

When profiling identifies repeated expensive closing tactics, add the SHRED
Lean package and wrap only those tactics:

```toml
# lakefile.toml
[[require]]
name = "shred"
path = "../shred/lean"
```

```lean
import SHRED

open LeanPrefix.AutomaticCertificate

example (x : Real) (h : x = 3) : x ^ 2 = 9 := by
  reuse_closing in nlinarith
```

Cache hits remain ordinary Lean proofs. SHRED requires an exact environment,
tactic, elaborated target, and ordered local context; then it infers the reused
proof's type and checks definitional equality with the current goal. A miss or
exception restores state and runs `nlinarith` unchanged.

## Scale and measured highlights

SHRED was developed against a self-contained DeepSeek-Prover rollout corpus:

| Measurement | Result |
|---|---:|
| Theorems | 9,655 |
| Registered proof proposals | 308,960 |
| Lean-correct proposals | 168,029 |
| Proposals eligible for conservative Lean-native splitting | 304,546 |
| Exact duplicate proposal occurrences | 42,815 |
| Eligible proposals sharing their first tactic | 53.71% |
| Lean tactic occurrences analyzed | 888,421 |
| Automatic certificate pairs checked in the representative study | 4,096 |
| Paired Lean-verdict agreement | 4,096 / 4,096 |
| Safe automatic certificate hits | 921 |
| Best measured certificate-transfer acceleration | 325.6× |

The repository includes immutable manifests, aggregate reports, deterministic
selection logic, proposal-level accounting, and hand-reviewed examples. Its
experiments ran on a 192-core Intel node with up to 766 GB RAM, using pinned
Lean, Mathlib, REPL, corpus, and Git revisions.

## Where this can matter most

SHRED's mechanisms are especially promising for workloads that create repeated
or deliberately branching proof computation:

- reinforcement-learning pipelines that verify large rollout groups;
- beam search, best-first search, and tree search with common partial proofs;
- synthetic algebra and arithmetic theorem families with repeated expensive
  closers such as `nlinarith`, `linarith`, `ring`, `omega`, or normalization;
- proof-generation services using best-of-N sampling;
- benchmark and dataset builders that repeatedly revisit related Lean states;
- interactive or hosted Lean systems that can amortize checked certificates
  across a long-running process.

A lightweight corpus profiler can use SHRED's measurements to determine whether
a workload has enough cost-weighted reuse to justify an execution cache before
building or deploying one.

## Architecture

The implementation has three auditable layers:

- **Lean-native instrumentation:** exact tactic boundaries, elaborated target
  and local-context keys, proof capture, type inference, definitional-equality
  checks, and transactional fallback.
- **Python orchestration:** streaming corpus readers, deterministic sampling,
  persistent REPL control, paired baseline/cached execution, timeout and memory
  isolation, and strict result consolidation.
- **Reproducible evidence:** self-contained compressed data shards, SHA-256
  manifests, frozen configurations, structured JSON reports, bootstrap
  intervals, and manual audits of successes and failure modes.

The certificate cache uses hashes only to locate candidate buckets. A hit still
requires exact structural equality, a compatible ordered local context,
successful proof-type inference, definitional equality with the target, and
ordinary Lean checking. Any exception restores the tactic state and runs the
original tactic.

## What the study discovered

The full corpus produced an important performance map. Exact shared prefixes
were common by count but represented only **3.762%** of cost-weighted execution
opportunity. In the representative certificate study, **22.85%** of
instrumented closing tactics hit the cache while total paired CPU fell
**3.2405%**. Many repeated steps were simply too cheap to dominate end-to-end
runtime.

At the same time, selected expensive closures saved tens to more than one
hundred CPU-seconds per reuse. This points to SHRED's strongest next design: a
cost-aware cache of named, shallow certificates for expensive proof tails,
rather than indiscriminate caching of every repeated tactic.

A subsequent compute-free gate tested that narrower hypothesis on 864 already
measured proposals from an arithmetic-heavy RL cohort. It saved 13.9% CPU
(1.16x), and even its 20.3% bootstrap upper bound missed the 36.7% reduction
required to justify a 1.5x held-out run. SHRED therefore stopped before spending
compute on the frozen C1 workload.

## Development and bundled evidence

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v

shred audit --manifest data/c0.manifest.json
shred analyze-exact --manifest data/c0.manifest.json
```

The same workflow is available as a typed Python API:

```python
from pathlib import Path
from shred import ProfileConfig, profile_workload

result = profile_workload(ProfileConfig(
    manifest=Path("data/c0.manifest.json"),
    lean_workspace=Path("/path/to/mathlib4"),
    output_dir=Path("artifacts/my-workload-profile"),
))
print(result.report["recommendation"])
```

The historical `lean-prefix` command remains available as a compatibility
alias. The complete C0 corpus is included as four deterministic gzip shards
under `data/c0/proofs/`; the auditor streams them without extraction and checks
both repository hashes and original uncompressed-source hashes.

## Evidence and design notes

- [`reports/c0_certificate_prevalence_d030.json`](reports/c0_certificate_prevalence_d030.json)
  - automatic certificate prevalence and paired CPU measurements
- [`reports/c0_certificate_prevalence_review.md`](reports/c0_certificate_prevalence_review.md)
  - hand audit of representative and expensive-tail cases
- [`docs/RL_BENCHMARK.md`](docs/RL_BENCHMARK.md)
  - exact held-out GRPO workload, prior-iteration admission rule, control, and
    no-compute feasibility gate
- [`reports/c0_rl_arithmetic_closure_admission.json`](reports/c0_rl_arithmetic_closure_admission.json)
  - machine-readable cohort characteristics and upper-sensitivity projection
- [`reports/c0_rl_retention_gate.json`](reports/c0_rl_retention_gate.json)
  - compute-free paired-overlap result that stops the larger C1 run
- [`docs/DESIGN.md`](docs/DESIGN.md) - execution and correctness model
- [`docs/VERIFICATION.md`](docs/VERIFICATION.md) - test and evidence contract
- [`docs/DATA.md`](docs/DATA.md) - immutable corpus and provenance
- [`docs/DECISIONS.md`](docs/DECISIONS.md) - scientific and engineering decisions
- [`docs/FUTURE.md`](docs/FUTURE.md) - cost-aware cache, serving, and acceleration roadmap

## Roadmap

- adapters for additional Lean rollout formats;
- named, shallow certificate storage for expensive closing-tactic families;
- cost-aware admission, eviction, and straggler isolation;
- integration adapters for Lean rollout and tree-search systems;
- Rust-native high-throughput orchestration and cache service;
- persistent and distributed certificate stores with complete attribution.

SHRED is built around a simple principle: optimize proof computation
aggressively, but never change the proof that Lean is asked to trust.
