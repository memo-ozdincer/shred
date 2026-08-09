# Automatic closing-certificate hand review

Date: 2026-08-09 Eastern

This review accompanies `c0_certificate_prevalence_d030.json`. D030 completely
measures the frozen 128-theorem representative stratum (4,096 proposals) and 31
of 32 enriched theorems (992 proposals). The missing enriched theorem is 41132,
the reduction-heavy `rfl` case already shown to exceed unchanged Lean limits in
D024. The enriched stratum is not a prevalence estimate.

## Representative decision

- 4,096/4,096 original-versus-cached verdicts agree.
- 921 automatic hits occur among 4,030 instrumented final tactics (22.85%).
- Baseline CPU is 1,492.63 seconds; cached CPU including telemetry queries is
  1,444.26 seconds.
- The paired saving is 48.37 seconds, or 3.24%, below the frozen 15% gate.
- A prior corrected representative execution (D029) measured 4.54%; both runs
  produce the same stop decision.
- Baseline and cached modes each record two timeouts and two process errors.

Hits are common but their value is concentrated. Representative `nlinarith`
hits account for 44.85 seconds saved across 170 hits. `linarith` contributes
7.40 seconds across 117 hits. Many cheap tactics are neutral: only 27 of 76
`exact` hits are positive, while 49 are negative. Removing the conservative
telemetry query cannot close the roughly 176-second gap to the 15% gate.

## Enriched observations

The completed 31-theorem enriched subset records 213 hits and 1,076.89 seconds
of paired CPU saving (19.90%). This number is intentionally selection-biased
and cannot override the representative result. Individual hits include:

- theorem 80508 candidate 13: 131.23 to 9.11 CPU seconds (122.12 saved);
- theorem 49452 candidate 23: 121.71 to 0.018 seconds (121.70 saved);
- theorem 24316 candidates 10 and 24: 26.19 and 27.68 seconds saved;
- theorem 81676 candidate 10: 13.13 seconds saved.

Two theorem-67057 `rfl` proposals are correct independently but fail when the
wrapper syntax is introduced, before runtime telemetry, at unchanged
`maxRecDepth`. D024 separately shows a huge inline `rfl` certificate that
reaches tactic application but fails ordinary declaration checking. These are
not hits and not speedups. `rfl` is therefore a registered source-level
fallback in the post-D030 code.

## Safety cases read by hand

- Multi-goal final tactics initially produced correct-to-incorrect outcomes
  because one certificate assigned only the main goal. The executable key now
  requires exactly one outstanding goal; authentic regression theorem 31182
  returns to 32/32 agreement with two explicit multi-goal fallbacks.
- A structured `·` block in theorem 9788 initially lost relative indentation
  under nesting. Exact native byte-range splicing plus a uniform two-space
  shift restores 32/32 agreement and preserves the complete block.
- Ten exact-key candidates reject certificate application and execute the
  original tactic; all representative verdicts remain unchanged.
- 200 reached final tactics reject capture because goals remain. They are
  misses/fallback work, never reported as certificates.
- Key hashes only select buckets. Every hit also requires exact structural key
  equality, local-count agreement, inferred proof type, definitional equality,
  and ordinary Lean acceptance.

## Decision and useful successor

Do not build the proposed general production cache: it fails the representative
15% end-to-end CPU gate despite a healthy hit rate. Preserve the implementation
as a research prototype and test fixture.

The evidence supports one narrower future experiment: named or otherwise
shallow certificates for expensive arithmetic/reduction tails, with cost-aware
admission and `rfl` excluded until shallow application is proved safe. That
project targets tail latency and selected tactic families; it is not a rescued
claim of general corpus-wide acceleration. Arbitrary non-closing state DAGs
remain unsupported.
