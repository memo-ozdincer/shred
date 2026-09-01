# OProver group capture protocol

Evidence label: **Observed implementation validation**, not a scientific
experiment and not performance evidence.

The pinned producer patch now carries exact OProver rollout siblings through a
single Kimina request and one fresh capture REPL lease. The client accepts only
IDs of the form `r{round}_p{prompt}_s{rollout}`, verifies identical formal
statements, submits each exact unique complete proof once, and explicitly marks
duplicate complete proofs as cached copies of a named representative.

Kimina prepares the common header once and executes every body from environment
`0`. Each returned proposal is annotated with the group ID, group position,
group size, and REPL UUID. The client checks the complete ID set, a single REPL
UUID, consistent group metadata, and either an all-captured or attributable
fallback result. It does not retry a group after uncertain transport.

Validation performed on 2026-09-01:

- every changed producer Python file passed `python -m py_compile`;
- the producer patch applied cleanly to OProver commit
  `b0cb2583b702d5040f84783ebba23d86241eac05`;
- applying the checked-in patch to a fresh clone reproduced the isolated source
  tree exactly; and
- all three server-side protocol tests passed in a disposable minimal Python
  environment built from the pinned source. They cover one-lease execution,
  attributable REPL acquisition failure, representative checkpoint pickling,
  shared receipt hashes, and ordered per-proposal results.

The full Verl training/verifier dependency stack was not installed. Its
client-side group-capture test remains static-only because importing that stack
would pull in NumPy and PyTorch. No Lean proof, dataset, rollout, model, or
benchmark was run for this protocol slice.

The source implementation now additionally captures a representative
checkpoint only for groups with at least eight unique attempts, a real shared
root environment, a nonempty exact native prefix, and remaining suffix work.
It hashes the parent-environment pickle, root-proof-state pickle, checkpoint
pickle, and canonical ordered exact source edges. This extension is exercised
by the passing server-side checkpoint test as well as static compilation and
exact patch round-trip validation.

The digest-only export is now checked in and covered by repository tests. Its
fixture proves native full/prefix CPU conversion, exact checkpoint mapping,
explicit existing-cache accounting, producer source immutability, declared
count reconciliation, no-overwrite behavior, failure on missing executed CPU,
and direct acceptance by `seal-authentic-trace`. This completes the static
producer-to-sealer path; it does not validate the unavailable OProver runtime.
