# Kernel finalization design review

Date: 2026-08-31

Evidence label: **Observed** pinned-source audit and **Hypothesis** design. No
Lean execution or performance experiment was performed.

## Novel question and decision map

Question: does portable checkpointing require a new trusted Lean capability, or
can a completed proof snapshot already be converted into an ordinary
kernel-checked declaration under the unchanged theorem statement?

Existing D-033 evidence cannot answer this because it checks in-process branch
verdicts, not cross-process proof materialization. The initial D-037 audit also
relied on the README's stale statement that completed proof states could not be
used further.

- If no root proof term or kernel API exists, stop portable checkpoints.
- If the proof can be checked only in the replayed environment, retain the
  mechanism as unsafe and stop.
- If the proof can be closed and checked in a clean pre-theorem environment,
  freeze that protocol and return to the authentic workload gate.

## Observed source path

At pinned REPL revision
`5d5c49d13dfc0c1d2df43a27c3e56e02ad81b9c3`:

1. `IO.processInput` returns the command state before and after the submitted
   command.
2. `runCommand` passes the pre-command environment into every tactic-mode
   `ProofSnapshot`. The source comment says this prevents self-reference.
3. `getProofStatus` reads the single root metavariable assignment, instantiates
   it, compares it with the root target, rejects metavariables, calls `addDecl`
   on an anonymous opaque definition, and then rejects `sorry` explicitly.
4. Lean's `Environment.addDecl` calls `addDeclCore`, documented as type checking
   and adding the declaration. Kernel failures include unknown constants,
   declaration/type mismatch, metavariables, free variables, time, memory, and
   recursion limits.
5. `ContextInfo` preserves `parentDecl?`; `LocalContext.getFVarIds` preserves
   ordered declarations; `mkLambdaFVars` and `mkForallFVars` provide the closure
   operations.

## Important gap in the current check

The anonymous completion check closes only free variables found in the proof.
For a theorem such as `theorem t (unused : Nat) : True`, a proof that does not
mention `unused` can be checked anonymously at type `True`, while the actual
theorem type is `Nat -> True`. This does not make the proof wrong—it can be
lambda-abstracted over `unused`—but it shows why the finalizer must abstract the
entire root local context and check the exact original theorem type.

The original internal name, universe parameters, and closed `TheoremVal` type
must also come from an independent elaboration of the unchanged theorem root.
Inferring a type from the completed proof is not sufficient for attribution.

## Result

**Observed:** proof extraction and kernel checking are already implemented in
the current REPL. The earlier description of a wholly missing materialization
bridge was too broad.

**Hypothesis:** exact named-theorem finalization needs no new trusted primitive.
A small protocol extension can retain authoritative target metadata, close all
root binders, and call the existing kernel checker on a clean parent
environment. Replayed constants remain outside the acceptance boundary.

**Decision:** correct D-037, freeze the protocol in
`docs/KERNEL_FINALIZATION.md`, and do not implement it until an authentic
read-only workload passes the value gate. A synthetic implementation probe
would now answer only an engineering question and is forbidden by D-036.
