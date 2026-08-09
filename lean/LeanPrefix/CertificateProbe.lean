import Mathlib

/-!
A deliberately manual feasibility probe for D-021.

This is not a production cache.  The caller supplies a key, and the probe only
tests whether a proof produced by a closing tactic can be abstracted over one
local context, instantiated in another, and accepted by ordinary Lean.  A real
cache would need a fail-closed environment, target, and local-context identity.
-/

open Lean Meta Elab Tactic

namespace LeanPrefix.CertificateProbe

structure Certificate where
  proof : Expr
  localCount : Nat

initialize certificateCache : IO.Ref (Lean.HashMap String Certificate) ← IO.mkRef ∅

def userLocals (context : LocalContext) : Array Expr :=
  context.getFVarIds.filterMap fun id =>
    let declaration := context.get! id
    if declaration.isImplementationDetail then none else some (mkFVar id)

syntax (name := captureClosing) "capture_closing " str " in " tactic : tactic
syntax (name := applyClosing) "apply_closing " str : tactic

elab_rules : tactic
| `(tactic| capture_closing $keySyntax:str in $inner:tactic) => withMainContext do
  let key := keySyntax.getString
  let goal ← getMainGoal
  let declaration ← goal.getDecl
  let locals := userLocals declaration.lctx
  evalTactic inner
  unless (← getGoals).isEmpty do
    throwError "capture_closing requires a tactic that closes every goal"
  let some proof := (← getMCtx).getExprAssignmentCore? goal
    | throwError "closing tactic did not assign the original goal"
  let proof ← instantiateMVars proof
  if proof.hasMVar then
    throwError "closing certificate contains unresolved metavariables"
  let abstracted ← mkLambdaFVars locals proof
  certificateCache.modify fun cache =>
    cache.insert key { proof := abstracted, localCount := locals.size }

elab_rules : tactic
| `(tactic| apply_closing $keySyntax:str) => withMainContext do
  let key := keySyntax.getString
  let some certificate := (← certificateCache.get).find? key
    | throwError "no closing certificate for key {key}"
  let goal ← getMainGoal
  let declaration ← goal.getDecl
  let locals := userLocals declaration.lctx
  unless locals.size == certificate.localCount do
    throwError "closing certificate local-context size mismatch"
  let proof := mkAppN certificate.proof locals
  let proofType ← inferType proof
  unless ← isDefEq proofType declaration.type do
    throwError "closing certificate type does not match the current goal"
  goal.assign proof
  replaceMainGoal []

end LeanPrefix.CertificateProbe
