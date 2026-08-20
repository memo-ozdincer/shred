# External repair corpus structural screen

Evidence labels in this review follow `AGENTS.md`. Exact counts and exact UTF-8
source-prefix positions are **Measured** by the checked-in analyzer and immutable
manifest. Source-position speedups are **Hypothesis** sensitivity calculations,
not verifier predictions. The stop is a **Decision**.

## Scope

This screen asks whether APRIL or LeanPolish already contains a typical Lean RL
repair workload promising enough to justify new Lean verification compute. It
does not invoke Lean, parse authoritative tactic boundaries, generate proposals,
or replay historical candidates. Raw files remain under ignored
`external-data/`.

The exact command is:

```bash
PYTHONPATH=src python -m lean_prefix.external_repair \
  --output reports/external_repair_structural_screen.json
```

Inputs and revisions are frozen in `data/external-repair.manifest.json`.

## APRIL

**Measured:** the frozen archive contains 260,103 rows with no malformed JSON,
rather than the 258,103 stated in its README. The split totals in the archive
are 249,005 train, 9,263 validation, and 1,835 test. Grouping by `src_hash`
produces 38,186 source-proof groups. Counting every distinct erroneous proof
plus every distinct correct proof gives a median of 6 candidates, with 11,913
groups containing at least 8 candidates.

The apparent batch size does not translate into a strong common proof prefix.
Across each whole `src_hash` group, the median earliest exact source divergence
is at byte zero. Using the explicitly non-authoritative `:= by` marker, only
445 of 38,177 eligible groups (1.17%) preserve at least half of the proof-body
source before their earliest divergence; 96 (0.25%) preserve at least 80%.
Forty source hashes also map to multiple distinct correct proof strings.

Pairwise erroneous/correct examples look better than whole groups, but each is
only a two-item correction pair, not a batch of alternative repairs to one
failing proof. APRIL also does not publish the Lean toolchain or Mathlib revision
needed to freeze a replay environment. It is useful repair-training data, but it
is not currently a clean SHRED performance benchmark.

## LeanPolish

**Measured:** all publisher-manifest logical hashes and row counts validate:
33,402 accepted rows plus 65,596 rejected rows, or 98,998 total. The screen
excludes 11,552 cleanup rows without an `attempt_id`, rather than merging their
missing identifiers. It also excludes 116 identifiers reused across corpora and
two groups without an accepted row.

There are 11,675 consistent identifiers with at least two distinct candidate
replacements. Their median batch contains 5 candidates. Removing whole-proof
`by` replacements leaves 4,722 local-edit groups, also with a median batch of 5.
Whole-file byte position is not a valid proxy for SHRED because a warm theorem
root already contains prior declarations and imports.

The Goedel shard can be anchored to pinned complete proof sources. Of 1,293
consistent local multi-candidate Goedel groups, 1,243 materialize exactly: the
complete source has the recorded byte length and the recorded original span at
the edit offset. Nineteen source proofs are absent and 31 have a size mismatch,
so they are explicitly excluded.

For the 1,243 anchored groups:

| Structural quantity | Result |
|---|---:|
| Median candidate count | 4 |
| Median raw proof-body source before divergence | 80.92% |
| Median comment-stripped, non-whitespace source before divergence | 36.14% |
| Groups with at least 50% non-trivia source before divergence | 439 |
| Groups with at least 80% non-trivia source before divergence | 140 |
| Groups with at least 8 candidates and at least 80% non-trivia prefix | 28 |
| Groups with at least 8 candidates and at least 90% non-trivia prefix | 8 |

The large raw-prefix number is mostly generated comments and formatting. This
is exactly why textual position cannot be promoted to executable prefix reuse.

## Sensitivity and gate

**Hypothesis:** if comment-stripped non-whitespace source position were equal to
the share of verifier CPU spent before divergence, and orchestration cost were
2% of independent verification, the 1,243 anchored Goedel groups would have a
median 1.260x sensitivity. Under that optimistic substitution, 393 groups reach
1.5x and 172 reach 2x. This is not a lower bound: tactic cost is highly uneven,
and the rejected LeanPolish siblings were not applied and verified as complete
files in the release.

**Decision:** do not run Lean or allocate cluster compute for APRIL or
LeanPolish. Neither dataset supplies Lean-native shared boundaries plus a
conservative cost-weighted lower bound above 1.5x. Selecting the 393 positive
source-position cases after inspection would be a favorable tail, not a typical
dataset result.

The most valuable next evidence would be already-existing attempt-level logs
from a repair/self-correction system containing complete revisions, ordinary
Lean verdicts, and per-tactic timing. Nemotron's unpublished failed refinement
turns or LeanPolish optimizer telemetry would fit; generating replacements or
replaying either corpus does not yet pass the compute gate.
