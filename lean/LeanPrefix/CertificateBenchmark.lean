import LeanPrefix.CertificateProbe

set_option maxHeartbeats 0
set_option profiler true
set_option profiler.threshold 0

open BigOperators Real Nat Topology Rat
open LeanPrefix.CertificateProbe

/- D021 group: different `ring_nf` scopes converge before the same `nlinarith`. -/
theorem certificate_source_81687
    (a b c d e f : ℝ)
    (ha : 1 ≤ a) (hb : 1 ≤ b) (hc : 1 ≤ c)
    (hd : 1 ≤ d) (he : 1 ≤ e) (hf : 1 ≤ f)
    (hab : a^2 * b^2 * c^2 * d^2 * e^2 * f^2 =
      (2 * a - 1) * (2 * b - 1) * (2 * c - 1) *
      (2 * d - 1) * (2 * e - 1) * (2 * f - 1)) :
    a + b + c + d + e + f ≥ 6 := by
  ring_nf at hab
  capture_closing "81687-nlinarith" in
    nlinarith [ha, hb, hc, hd, he, hf, hab]

theorem certificate_target_81687
    (a b c d e f : ℝ)
    (ha : 1 ≤ a) (hb : 1 ≤ b) (hc : 1 ≤ c)
    (hd : 1 ≤ d) (he : 1 ≤ e) (hf : 1 ≤ f)
    (hab : a^2 * b^2 * c^2 * d^2 * e^2 * f^2 =
      (2 * a - 1) * (2 * b - 1) * (2 * c - 1) *
      (2 * d - 1) * (2 * e - 1) * (2 * f - 1)) :
    a + b + c + d + e + f ≥ 6 := by
  ring_nf at *
  apply_closing "81687-nlinarith"

/- D021 group: redundant normalization preambles converge before `positivity`. -/
theorem certificate_source_24316
    (a b c : ℝ) (ha : a > 0) (hb : b > 0) (hc : c > 0) :
    (1 + 2 * a / (b + c)) * (1 + 2 * b / (c + a)) *
      (1 + 2 * c / (a + b)) ≥ 2 := by
  apply le_of_sub_nonneg
  ring_nf
  field_simp [ha.ne', hb.ne', hc.ne']
  ring_nf
  capture_closing "24316-positivity" in positivity

theorem certificate_target_24316
    (a b c : ℝ) (ha : a > 0) (hb : b > 0) (hc : c > 0) :
    (1 + 2 * a / (b + c)) * (1 + 2 * b / (c + a)) *
      (1 + 2 * c / (a + b)) ≥ 2 := by
  simp [add_comm]
  norm_num
  apply le_of_sub_nonneg
  ring_nf
  field_simp [ha.ne', hb.ne', hc.ne']
  ring_nf
  apply_closing "24316-positivity"
