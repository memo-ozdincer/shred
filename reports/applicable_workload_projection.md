# Projection for a well-applicable SHRED workload

Evidence label: **Hypothesis**. This is a reproducible sensitivity calculation,
not a measured corpus result or a deployment claim.

## Concrete RL workload

The generic sensitivity range now has a concrete target. A rule using only C0
independent-execution telemetry admits 505 arithmetic theorem groups with
16,160 proposals. Conservative repeated `nlinarith`, `linarith`, and
`positivity` closure cost is 49.539% of their full verification CPU. The
held-out evaluation input is the corresponding 16,160-proposal slice of the
completed C1 GRPO verifier stream, frozen before any C1 cached timing is read.

At the slower 27.05x transfer anchor and 2% overhead, retaining 100% of that
upper signal gives **45.7% less CPU and 1.84x CPU-equivalent throughput**. This
is an upper-sensitivity point, not a conservative forecast. See
`docs/RL_BENCHMARK.md` for the compute-free retention gate that must pass before
any C1 execution is authorized.

## Result

A typical workload where SHRED is very well-applicable would spend a substantial
share of verification time repeatedly generating the same expensive closing
certificates. Under that workload shape, the current evidence supports the
following planning range:

| Baseline CPU in reusable expensive closers | Projected CPU reduction | Projected throughput |
|---:|---:|---:|
| 25% | 22.1%–22.9% | 1.28×–1.30× |
| 40% | 36.5%–37.9% | 1.58×–1.61× |
| 60% | 55.8%–57.8% | 2.26×–2.37× |
| 80% | 75.0%–77.8% | 4.01×–4.50× |

The table is a sensitivity analysis, not headline evidence. A workload with
40%–60% *realized* reusable expensive-closer CPU would yield 1.6x–2.3x
throughput in this model, but an offline upper bound on repeated edges does not
establish that realized share.

## Model

The calculation uses

```text
projected CPU fraction = 1 - f + f / A + o
projected throughput   = 1 / projected CPU fraction
```

where `f` is the share of end-to-end baseline CPU in repeated eligible
expensive closers, `A` is measured certificate generation-plus-check divided by
application-plus-check acceleration, and `o` is additional cache/orchestration
overhead. The table uses 2% overhead and the measured successful-transfer range
of 27.05× to 325.18×. Above roughly 27×, the workload's reusable CPU share
matters much more than the exact per-hit acceleration.

At the conservative 27.05× anchor and 2% overhead, the model requires reusable
expensive closers to account for 36.7% of baseline CPU for 1.5× throughput,
54.0% for 2×, 71.3% for 3×, and 80.0% for 4×.

## Evidence anchors and boundary

- **Measured:** The representative D030 study preserved 4,096/4,096 paired
  verdicts, recorded 921 hits, and reduced CPU by 3.24%, equivalent to 1.033×
  throughput from CPU alone.
- **Observed diagnostic:** The deliberately enriched D030 subset reduced CPU by
  19.90%, equivalent to 1.248×, but was incomplete and contained two verdict
  disagreements. It is not a correctness or prevalence result.
- **Measured:** The bounded D025 transfer benchmark measured 27.05× for
  `positivity` and 325.18× for `nlinarith`, including generation/check versus
  application/check.
- **Hypothesis:** The table reweights computation toward repeated expensive
  closers. No existing dataset is relabeled as representative of that workload.

The projection does not assume that every tactic is reusable. Misses, first
captures, unsupported contexts, ordinary Lean checking, and the unchanged
remainder of proof execution are represented by the non-reusable fraction and
the explicit overhead term. A real claim still requires an immutable workload,
zero paired verdict disagreements, and an end-to-end benchmark against warm
independent execution.

## Reproduction

```bash
PYTHONPATH=src python -m lean_prefix.projection
```

Inputs:

- `reports/c0_certificate_prevalence_d030.json`, SHA-256
  `efe23e5c17b4ab60cdc972f08bcf2cbf42a36c0deb9b3c26191c679c6a32a2a1`
- `reports/c0_certificate_probe.json`, SHA-256
  `4a77f798236c236f874aa4e237f77c2ead835ba6d31445380d6cdc85ced72fa1`
