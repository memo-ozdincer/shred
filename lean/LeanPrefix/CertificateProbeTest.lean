import LeanPrefix.CertificateProbe

open LeanPrefix.CertificateProbe

example (x : Nat) : x = x := by
  capture_closing "self-test-rfl" in rfl

example (x : Nat) : x = x := by
  apply_closing "self-test-rfl"

example (x : Int) (h : x > 0) : x ≥ 0 := by
  capture_closing "self-test-omega" in omega

example (x : Int) (h : x > 0) : x ≥ 0 := by
  apply_closing "self-test-omega"
