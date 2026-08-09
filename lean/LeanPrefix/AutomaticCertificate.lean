import Mathlib

/-!
An experimental, fail-closed closing-certificate cache for D-023.

This module does not identify goals by pretty printing.  It abstracts the
elaborated target over the ordered user-visible local context and retains the
exact structural tactic syntax.  A hash only selects a bucket; an exact key
comparison and ordinary Lean type checking remain mandatory for every hit.
-/

open Lean Meta Elab Tactic

namespace LeanPrefix.AutomaticCertificate

def environmentFingerprint : String :=
  "lean=4.9.0-rc1;mathlib=2f65ba7f1a9144b20c8e7358513548e317d26de1;context=c0-v1"

/-- A source-location-free, trivia-free representation of tactic syntax. -/
partial def syntaxIdentity : Syntax → String
  | .missing => "missing"
  | .atom _ value => s!"atom({value.length}):{value}"
  | .ident _ _ value preresolved =>
      s!"ident:{reprStr value}:{reprStr preresolved}"
  | .node _ kind arguments =>
      let children := arguments.toList.map syntaxIdentity
      s!"node:{reprStr kind}:[{String.intercalate "," children}]"

structure Key where
  environment : String
  tactic : String
  target : Expr

def Key.hash (key : Key) : UInt64 :=
  mixHash (mixHash key.environment.hash key.tactic.hash) key.target.hash

def Key.exactEq (left right : Key) : Bool :=
  left.environment == right.environment &&
    left.tactic == right.tactic &&
    left.target == right.target

structure Certificate where
  key : Key
  proof : Expr
  localCount : Nat

initialize certificateCache : IO.Ref (Lean.HashMap UInt64 (Array Certificate)) ←
  IO.mkRef ∅

initialize lastEvents : IO.Ref (Array String) ← IO.mkRef #[]

def userLocals (context : LocalContext) : Array Expr :=
  context.getFVarIds.filterMap fun id =>
    let declaration := context.get! id
    if declaration.isImplementationDetail then none else some (mkFVar id)

def elapsedNanos (start finish : Nat) : Nat := finish - start

def emit (event : String) (fields : Array (String × String) := #[]) : TacticM Unit := do
  let suffix := String.intercalate " " <|
    fields.toList.map fun (name, value) => s!"{name}={value}"
  let line := s!"LEAN_PREFIX_CERT event={event} {suffix}"
  lastEvents.modify fun events => events.push line
  logInfo m!"{line}"

def makeKey (tactic : String) : TacticM (Option (Key × Array Expr)) :=
  withMainContext do
    if (← getGoals).length != 1 then
      return none
    let goal ← getMainGoal
    let declaration ← goal.getDecl
    let locals := userLocals declaration.lctx
    let target ← instantiateMVars declaration.type
    if target.hasMVar || target.hasLevelMVar then
      return none
    let abstracted ← instantiateMVars (← mkForallFVars locals target)
    if abstracted.hasMVar || abstracted.hasLevelMVar || abstracted.hasFVar then
      return none
    return some ({ environment := environmentFingerprint, tactic, target := abstracted }, locals)

def findCertificate (key : Key) : IO (Option Certificate) := do
  let bucket := (← certificateCache.get).findD key.hash #[]
  return bucket.find? fun certificate => certificate.key.exactEq key

def insertCertificate (certificate : Certificate) : IO Unit :=
  certificateCache.modify fun cache =>
    let bucket := cache.findD certificate.key.hash #[]
    if bucket.any fun existing => existing.key.exactEq certificate.key then
      cache
    else
      cache.insert certificate.key.hash (bucket.push certificate)

def runAndCapture
    (key : Key) (locals : Array Expr) (goal : MVarId) (inner : TSyntax `tactic) :
    TacticM Unit := do
  let generatorStart ← IO.monoNanosNow
  evalTactic inner
  let generatorFinish ← IO.monoNanosNow
  unless (← getGoals).isEmpty do
    emit "capture_rejected" #[
      ("key", toString key.hash),
      ("reason", "remaining_goals"),
      ("generator_ns", toString (elapsedNanos generatorStart generatorFinish))
    ]
    return
  let captureStart ← IO.monoNanosNow
  let some proof := (← getMCtx).getExprAssignmentCore? goal
    | emit "capture_rejected" #[("key", toString key.hash), ("reason", "unassigned")]
      return
  let proof ← instantiateMVars proof
  if proof.hasMVar || proof.hasLevelMVar then
    emit "capture_rejected" #[("key", toString key.hash), ("reason", "metavariable")]
    return
  let abstracted ← instantiateMVars (← mkLambdaFVars locals proof)
  if abstracted.hasMVar || abstracted.hasLevelMVar || abstracted.hasFVar then
    emit "capture_rejected" #[("key", toString key.hash), ("reason", "free_or_meta")]
    return
  insertCertificate { key, proof := abstracted, localCount := locals.size }
  let captureFinish ← IO.monoNanosNow
  emit "capture" #[
    ("key", toString key.hash),
    ("generator_ns", toString (elapsedNanos generatorStart generatorFinish)),
    ("capture_ns", toString (elapsedNanos captureStart captureFinish))
  ]

syntax (name := reuseClosing) "reuse_closing " "in " tactic : tactic
syntax (name := certificateEvents) "#lean_prefix_certificate_events" : command

elab_rules : command
| `(#lean_prefix_certificate_events) => do
  for event in ← lastEvents.get do
    logInfo m!"{event}"
  lastEvents.set #[]

elab_rules : tactic
| `(tactic| reuse_closing in $inner:tactic) => withMainContext do
  lastEvents.set #[]
  let keyStart ← IO.monoNanosNow
  let tactic := syntaxIdentity inner.raw
  let saved ← saveState
  let keyAttempt ← try
    pure (some (← makeKey tactic))
  catch _ =>
    restoreState saved
    pure none
  let keyFinish ← IO.monoNanosNow
  let some keyResult := keyAttempt
    | emit "uncacheable" #[
        ("reason", "key_error"),
        ("key_ns", toString (elapsedNanos keyStart keyFinish))
      ]
      evalTactic inner
      return
  let some (key, locals) := keyResult
    | emit "uncacheable" #[("reason", "nonclosed_context")]
      evalTactic inner
      return
  let lookupStart ← IO.monoNanosNow
  let certificate ← findCertificate key
  let lookupFinish ← IO.monoNanosNow
  let keyFields := #[
    ("key", toString key.hash),
    ("key_ns", toString (elapsedNanos keyStart keyFinish)),
    ("lookup_ns", toString (elapsedNanos lookupStart lookupFinish))
  ]
  match certificate with
  | none =>
      emit "miss" keyFields
      let goal ← getMainGoal
      runAndCapture key locals goal inner
  | some certificate =>
      let saved ← saveState
      let applicationStart ← IO.monoNanosNow
      let applied ← try
        let goal ← getMainGoal
        let declaration ← goal.getDecl
        unless locals.size == certificate.localCount do
          throwError "closing certificate local-context size mismatch"
        let proof := mkAppN certificate.proof locals
        let proofType ← inferType proof
        unless ← isDefEq proofType declaration.type do
          throwError "closing certificate type mismatch"
        goal.assign proof
        replaceMainGoal []
        pure true
      catch _ =>
        restoreState saved
        pure false
      let applicationFinish ← IO.monoNanosNow
      if applied then
        emit "hit" <| keyFields.push (
          "application_ns", toString (elapsedNanos applicationStart applicationFinish))
      else
        emit "application_rejected" <| keyFields.push (
          "application_ns", toString (elapsedNanos applicationStart applicationFinish))
        let goal ← getMainGoal
        runAndCapture key locals goal inner

end LeanPrefix.AutomaticCertificate
