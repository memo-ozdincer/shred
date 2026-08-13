# Contributing to SHRED

SHRED treats correctness preservation and performance evidence as separate
release gates. Contributions must keep ordinary Lean as the final authority
and must not trade verdict fidelity for cache hits.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
```

Lean integration work additionally requires the pinned toolchain and a
Mathlib workspace. See `docs/COMPUTE.md` and `docs/VERIFICATION.md` before
running performance experiments.

## Pull requests

- Keep correctness, profiling, and experimental changes in separable commits.
- Add explicit fallback behavior for unsupported Lean syntax or state.
- Add tests for verdict attribution, failure, timeout, and cache isolation.
- Report proposal counts, verdict agreement, CPU time, wall time, and fallback
  counts for performance claims.
- Record scientific or architectural choices in `docs/DECISIONS.md`.
- Do not commit private rollout data, credentials, or raw cluster artifacts.

The operating contract in `AGENTS.md` applies to automated contributions and
is also the concise statement of the project's experimental invariants.
