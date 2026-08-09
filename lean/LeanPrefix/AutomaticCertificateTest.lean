import LeanPrefix.AutomaticCertificate

set_option maxHeartbeats 0

open LeanPrefix.AutomaticCertificate

/- Whitespace and comments do not alter structural tactic identity. -/
example (n : Nat) : n = n := by
  reuse_closing in rfl

example (n : Nat) : n = n := by
  reuse_closing in
    -- deliberately different trivia
    rfl

/- A materially different tactic is a miss even at the same target. -/
example (n : Nat) : n = n := by
  reuse_closing in exact Eq.refl n

/- A dependency-changing local reorder is not treated as the same context. -/
example (n : Nat) (h : n = 0) : n = 0 := by
  reuse_closing in exact h

example (h : (0 : Nat) = 0) (n : Nat) : 0 = 0 := by
  reuse_closing in exact Eq.refl 0

/- Local instance binder information participates in the abstracted target. -/
example {α : Type} [Inhabited α] (x : α) : Nonempty α := by
  reuse_closing in exact ⟨x⟩

example {α : Type} (x : α) : Nonempty α := by
  reuse_closing in exact ⟨x⟩

/- A tactic that closes sibling goals is executed unchanged and never cached. -/
example : True ∧ True := by
  constructor
  reuse_closing in all_goals trivial
