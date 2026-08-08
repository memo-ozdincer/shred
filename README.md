# Lean Prefix

Lean Prefix is an experimental execution engine for checking batches of
complete Lean proofs by evaluating their exact common tactic prefixes once.

Today, 32 attempts for one theorem are usually checked as 32 unrelated Lean
programs. Lean Prefix represents them as a prefix trie, preserves the Lean
state at each shared node, and forks only where the attempts diverge. Every
leaf still receives an ordinary Lean verdict.

```text
theorem root
├── simp [foo]
│   ├── nlinarith
│   ├── ring
│   └── positivity
└── norm_num
```

The project asks one question:

> Given exactly the same complete proof attempts, can exact shared-prefix
> execution return exactly the same Lean verdicts with materially less work?

## Starting evidence

The source corpus contains 9,655 theorems and 308,960 registered proposals from
a frozen DeepSeek-Prover C0 rollout. A preliminary read-only analysis using the
source project's operational proof-step parser observed:

- 42,815 exact duplicate proposals (13.9%);
- 53.6% of proposals sharing an exact first parsed step with another proposal
  for the same theorem;
- 913,966 parsed step occurrences versus 712,284 distinct prefix-trie nodes;
- an unweighted 1.28x oracle ratio, or 201,682 repeated step occurrences.

These are **observations**, not repository-reproduced measurements and not a
speedup claim. Cheap and expensive tactics are weighted equally in that count.
The first milestones reproduce the corpus and then replace heuristic parsing
with Lean-native boundaries and cost-weighted measurements.

## Scientific boundary

Version one shares only exact rooted prefixes for the same theorem and pinned
Lean environment. It does not guess that two proofs are similar, merge states
reached by different syntax, alter tactics, or weaken verification. Unsupported
proofs use the independent fallback and remain in all accounting.

See:

- [`docs/PROJECT_CHARTER.md`](docs/PROJECT_CHARTER.md) — claim, success, and non-goals
- [`docs/PLAN.md`](docs/PLAN.md) — gated implementation sequence
- [`docs/DESIGN.md`](docs/DESIGN.md) — intended execution model
- [`docs/VERIFICATION.md`](docs/VERIFICATION.md) — tests and evidence required
- [`docs/DATA.md`](docs/DATA.md) — immutable C0 source and data handling
- [`docs/FUTURE.md`](docs/FUTURE.md) — deliberately deferred extensions
- [`AGENTS.md`](AGENTS.md) — operating contract

## Repository status

Bootstrap stage. The only executable functionality is an immutable-corpus
auditor and a pure prefix-trie accounting primitive. No performance result or
Lean execution-engine result is claimed yet.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
lean-prefix audit --manifest data/c0.manifest.json
```

The complete C0 corpus is included as four deterministic gzip shards under
`data/c0/proofs/`. The auditor streams them without extraction and verifies
both their repository hashes and the original uncompressed source hashes.
