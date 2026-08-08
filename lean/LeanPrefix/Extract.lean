import Mathlib
import Mathlib.Tactic.Says

open Lean Parser

namespace LeanPrefix

structure Request where
  proposalId : String
  proof : String
  deriving FromJson

structure TacticUnit where
  startByte : Nat
  stopByte : Nat
  text : String
  syntaxKind : String
  deriving ToJson

structure Response where
  proposalId : String
  eligible : Bool
  units : Array TacticUnit := #[]
  error : Option String := none
  deriving ToJson

def proofBody (proof : String) : String :=
  (proof.splitOn "```").headD proof

partial def outerTacticSequence? (stx : Syntax) : Option Syntax := do
  if stx.getKind == ``Lean.Parser.Tactic.tacticSeq1Indented then
    return stx
  if stx.getKind == ``Lean.Parser.Tactic.tacticSeqBracketed then
    return stx
  for arg in stx.getArgs do
    if let some result := outerTacticSequence? arg then
      return result
  none

def sequencePayload (sequence : Syntax) : Syntax :=
  if sequence.getNumArgs == 1 && sequence[0].isOfKind nullKind then
    sequence[0]
  else
    sequence

def hasTopLevelSemicolon (sequence : Syntax) : Bool :=
  (sequencePayload sequence).getArgs.any fun stx => stx.isAtom && stx.getAtomVal == ";"

def tacticArguments (sequence : Syntax) : Array Syntax :=
  (sequencePayload sequence).getSepArgs

def extractUnit (source : String) (stx : Syntax) : Except String TacticUnit := do
  let some range := stx.getRange?
    | throw "tactic has no canonical source range"
  if range.stop.byteIdx > source.utf8ByteSize then
    throw s!"tactic range ends beyond input: {range.stop.byteIdx} > {source.utf8ByteSize}"
  return {
    startByte := range.start.byteIdx
    stopByte := range.stop.byteIdx
    text := source.extract range.start range.stop
    syntaxKind := stx.getKind.toString
  }

def extract (env : Environment) (request : Request) : Response :=
  let body := proofBody request.proof
  match Mathlib.Tactic.Says.parseAsTacticSeq env body with
  | .error error => { proposalId := request.proposalId, eligible := false, error := some error }
  | .ok stx =>
      match outerTacticSequence? stx.raw with
      | none => {
          proposalId := request.proposalId
          eligible := false
          error := some s!"parsed tactic sequence has unsupported root kind {stx.raw.getKind}"
        }
      | some sequence =>
          if sequence.isOfKind ``Lean.Parser.Tactic.tacticSeqBracketed then
            {
              proposalId := request.proposalId
              eligible := false
              error := some "bracketed root tactic sequence requires independent fallback"
            }
          else if hasTopLevelSemicolon sequence then
            {
              proposalId := request.proposalId
              eligible := false
              error := some "top-level semicolon sequence requires independent fallback"
            }
          else match (tacticArguments sequence).mapM (extractUnit body) with
          | .error error => {
              proposalId := request.proposalId
              eligible := false
              error := some error
            }
          | .ok units => {
              proposalId := request.proposalId
              eligible := !units.isEmpty
              units := units
              error := if units.isEmpty then some "parsed tactic sequence is empty" else none
            }

def processLine (env : Environment) (line : String) : Response :=
  match Json.parse line >>= fromJson? with
  | .error error => {
      proposalId := ""
      eligible := false
      error := some s!"invalid request: {error}"
    }
  | .ok request => extract env request

def serve (env : Environment) (input output : IO.FS.Stream) : IO Unit := do
  let mut done := false
  while !done do
    let line ← input.getLine
    if line.isEmpty then
      done := true
    else
      output.putStr ((toJson (processLine env line)).compress ++ "\n")
      output.flush

unsafe def run : IO Unit := do
  let env ← importModules #[{ module := `Mathlib }] {} 0 (leakEnv := true)
  IO.eprintln "lean-prefix-extract: ready"
  serve env (← IO.getStdin) (← IO.getStdout)

end LeanPrefix

unsafe def main : IO Unit := LeanPrefix.run
