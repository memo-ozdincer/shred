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

The project asked one question:

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
Cheap, expensive, and never-reached tactics are weighted equally. The corrected
cost profiler measured an unchanged complete-proof baseline and used Lean's
in-process C profiler for conservative reached-prefix attribution. The complete
308,960-proposal census estimates only 3.762% exact-prefix opportunity
(bootstrap 3.401%–4.159%), far below the frozen 15% gate. The strict summarizer
also correctly refuses a claim because of three historical C0-label
disagreements and 20 process deaths. The version-one executor is therefore
stopped rather than implemented.

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

Phase 1 characterization and the complete Phase 2 census are finished. No
execution-engine speedup is claimed, and Phases 3–6 are stopped by the failed
gate. A bounded top-ten diagnostic found visible reconvergence, but on an
intentionally enriched sample and with printed goals that omit hidden Lean
state. The next permitted question is narrower: whether a closing proof
certificate can be reapplied and checked by ordinary Lean materially faster
than regenerating the tactic result. No proof-state-DAG or semantic cache is
currently claimed or authorized.

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
