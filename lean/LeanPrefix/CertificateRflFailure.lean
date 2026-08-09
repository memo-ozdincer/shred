import LeanPrefix.CertificateProbe

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat
open LeanPrefix.CertificateProbe

/-!
Negative D024 case. The source succeeds, but applying its large in-memory proof
expression in the target exceeds Lean's unchanged default `maxRecDepth`. This
file is intentionally expected to fail and is excluded from the passing D025
benchmark. Raising the verifier limit would change the registered environment.
-/

theorem certificate_source_41132 (n : ℕ) :
    ∑ m in Finset.range (500 + 1), (-1 : ℤ)^m * choose 1000 (2*m) = 2^500 := by
  rw [Finset.sum_eq_multiset_sum]
  capture_closing "41132-rfl" in rfl

theorem certificate_target_41132 (n : ℕ) :
    ∑ m in Finset.range (500 + 1), (-1 : ℤ)^m * choose 1000 (2*m) = 2^500 := by
  simp only [Finset.sum, Finset.mem_range]
  apply_closing "41132-rfl"
