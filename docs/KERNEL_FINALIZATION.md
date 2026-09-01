# Kernel-authoritative checkpoint finalization

Status: source-supported design; no implementation or execution is authorized.

## Correction to the initial audit

The pinned Lean REPL does more than report that no tactic goals remain.
`getProofStatus` retrieves the root metavariable assignment, instantiates
metavariables, checks its type against the root goal, rejects residual
metavariables, constructs an anonymous opaque definition, calls Lean's
`addDecl`, and then rejects `sorry`. `Environment.addDecl` invokes the kernel
type checker; the explicit later `sorry` check is still required.

Therefore proof extraction and kernel checking already exist in a narrow form.
The missing bridge is exact finalization of the original named theorem against
an independently reconstructed pre-theorem environment.

## Supported version-one declaration class

Portable finalization initially supports only a single ordinary `theorem` or
`lemma` with one tactic-mode root goal. The theorem statement, namespaces,
sections, options, imports, preceding commands, and exact tactic syntax remain
unchanged. The command that creates the root must have no error messages.

The following fall back to complete independent verification:

- multiple, nested, term-mode, or unresolved `sorry` sites;
- `example`, `def`, `opaque`, `abbrev`, mutual, recursive, unsafe, or partial
  declarations;
- commands after the target whose behavior depends on target attributes;
- roots whose complete pre-theorem command environment cannot be reconstructed;
- target metadata, local-context, or environment digest disagreement;
- completed proofs with metavariables, free variables, or `sorry` after closure;
- any declaration or auxiliary constant absent from the clean parent
  environment; and
- every load, timeout, crash, kernel error, or accounting ambiguity.

This is an eligibility boundary, not a claim that excluded syntax is invalid.

## Required root capture

When the original command is elaborated with its proof hole, retain:

- the clean command snapshot immediately before the target declaration;
- the post-elaboration target `TheoremVal`: internal name, universe parameters,
  and closed type;
- `ContextInfo.parentDecl?` and the exact target syntax digest;
- the root metavariable identifier, ordered root local context, root target,
  options, and resource limits;
- all root command messages; and
- digests of the parent environment and every field in the portable checkpoint
  envelope.

The current REPL already passes the pre-command environment into
`ProofSnapshot.create`, specifically to prevent theorem self-reference. The
new metadata must be serialized beside, not inferred from, pretty-printed
goals.

For input containing helper declarations before the theorem, capture a
Lean-native command snapshot immediately before the theorem. Treating the
header-only environment as the parent would omit those helpers and must miss.

## Finalization protocol

1. Verify the checkpoint envelope, trusted producer signature, artifact digest,
   exact compatibility identity, source bytes, and resource profile.
2. In a disposable consumer, independently rebuild the clean parent
   environment from pinned imports and exact commands. Do not use replayed
   pickle constants as the kernel authority.
3. Independently elaborate the unchanged theorem header with a proof hole only
   to recover authoritative target metadata. Retain the clean parent snapshot;
   do not accept the theorem containing the hole.
4. Require the authoritative target name, universe parameters, closed type,
   parent-environment digest, and root-context digest to match the envelope.
5. Load the trusted proof snapshot in the isolated work environment and execute
   the unchanged suffix under the original limits.
6. Require exactly one original root goal and no remaining tactic goals. Read
   its assignment and instantiate all metavariables.
7. In the root goal context, abstract the entire ordered root local context—not
   only variables occurring in the proof—over both the proof and target. This
   preserves unused theorem parameters and dependent binder order.
8. Require the closed proof type to be definitionally equal to the authoritative
   original theorem type. Reject residual metavariables, free variables, and
   `sorry`.
9. Construct `Declaration.thmDecl` using the authoritative original name,
   universe parameters, and type, with the closed proof as its value.
10. Call `Environment.addDecl` on the independently rebuilt clean parent
    environment with the original kernel options and limits.
11. Return acceptance only when that kernel call succeeds and the original root
    command produced no errors. Otherwise return the independently verified
    fallback verdict, with the finalization failure explicitly counted.

The clean kernel call naturally rejects proof terms that refer to constants
created only inside the replayed or tactic-mutated environment.

## Why the existing anonymous check is insufficient

The existing code abstracts only free variables that happen to occur in the
proof. An unused theorem parameter can therefore disappear from the anonymous
definition type. It also infers that declaration's type from the proof rather
than requiring the exact original theorem declaration.

That is a useful completion sanity check, but it is not yet an attributable
verdict for the unchanged named theorem. Full-root abstraction and exact target
metadata close this gap.

## Static feasibility result

All core operations required by the protocol are present in the pinned Lean
sources:

- `ContextInfo.parentDecl?` identifies the surrounding declaration;
- the REPL retains the pre-command environment for tactic-mode roots;
- the root assignment and full local context survive proof-state pickling;
- `instantiateMVars`, `mkLambdaFVars`, and `mkForallFVars` close the proof and
  target; and
- `Environment.addDecl` performs the kernel check and reports unknown
  constants, free variables, metavariables, type mismatch, timeout, memory, and
  recursion failures.

**Hypothesis:** no new trusted Lean primitive is required. The bridge is a
bounded REPL protocol and metadata change. This lowers mechanism risk, but it
does not establish authentic workload value and does not authorize a run.
