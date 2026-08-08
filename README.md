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

## Measured discovery evidence

The self-contained source corpus has 9,655 theorems and 308,960 registered
proposals from a frozen DeepSeek-Prover C0 rollout. Checked-in analyses measure:

- 42,815 exact duplicate proposal occurrences (13.86%);
- 304,546 proposals (98.57%) eligible for conservative Lean-native splitting;
- 53.71% of eligible proposals sharing an exact first tactic prefix with
  another proposal for the same theorem;
- 888,421 eligible tactic occurrences versus 689,193 exact prefix-trie nodes;
- an unweighted 1.289x oracle ratio, or 199,228 repeated tactic occurrences.

These are **measured syntax-level opportunity counts**, not a speedup claim.
Cheap, expensive, and never-reached tactics are weighted equally. The cost
profiler needed to resolve that uncertainty is implemented and integration
tested; the complete C0 replay is the next evidence-producing run.

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
- [`docs/STATUS.md`](docs/STATUS.md) — completed and next milestones
- [`docs/COMPUTE.md`](docs/COMPUTE.md) — Phase 2 CPU runbook
- [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md) — exact current state and recovery
- [`docs/FUTURE.md`](docs/FUTURE.md) — deliberately deferred extensions
- [`AGENTS.md`](AGENTS.md) — operating contract

## Repository status

Phase 1 characterization and the Phase 2 replay-profiler implementation are
complete. The profiler verifies every complete proof independently, replays
every eligible proof from an immutable theorem-root state, and records reached
tactic cost and agreement. The full-corpus Phase 2 measurement has not yet
run, and no execution-engine speedup is claimed.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
lean-prefix audit --manifest data/c0.manifest.json
lean-prefix analyze-exact --manifest data/c0.manifest.json
```

The complete C0 corpus is included as four deterministic gzip shards under
`data/c0/proofs/`. The auditor streams them without extraction and verifies
both their repository hashes and the original uncompressed source hashes.
