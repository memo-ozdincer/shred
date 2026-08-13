# Security and correctness

SHRED executes generated Lean source and should only be run inside the same
resource and trust boundary you would use for ordinary Lean verification.
Use process isolation, timeouts, and memory limits for untrusted workloads.

Do not report ordinary malformed proofs or expected cache misses as security
issues. Report cases where SHRED:

- returns an acceptance that ordinary Lean rejects;
- crosses theorem, environment, or local-context boundaries;
- fails to restore tactic state before fallback;
- attributes one proposal's verdict to another proposal; or
- bypasses configured process limits.

Until a private reporting address is published, open a GitHub issue containing
only a minimal non-sensitive reproducer. Do not attach private proof corpora,
cluster credentials, or proprietary theorem statements.
