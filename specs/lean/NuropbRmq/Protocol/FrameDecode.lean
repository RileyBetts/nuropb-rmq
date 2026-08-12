/-!
Bounded frame-decode acceptance predicate (Protocol invariant 6).
``frame_max`` bounds total wire size (payload + 8).
-/

namespace NuropbRmq.Protocol

/-- ``size`` is payload length; acceptance requires payload+8 ≤ frameMax. -/
def decodeAccepted (size depth frameMax maxTableDepth : Nat) : Bool :=
  decide (size + 8 ≤ frameMax) && decide (depth ≤ maxTableDepth)

theorem decodeAccepted_implies_bounds
    (size depth frameMax maxTableDepth : Nat)
    (h : decodeAccepted size depth frameMax maxTableDepth = true) :
    size + 8 ≤ frameMax ∧ depth ≤ maxTableDepth := by
  simp [decodeAccepted, Bool.and_eq_true] at h
  exact h

theorem decodeAccepted_of_bounds
    (size depth frameMax maxTableDepth : Nat)
    (hs : size + 8 ≤ frameMax) (hd : depth ≤ maxTableDepth) :
    decodeAccepted size depth frameMax maxTableDepth = true := by
  simp [decodeAccepted, hs, hd]

theorem decodeAccepted_reject_oversize
    (size depth frameMax maxTableDepth : Nat)
    (h : frameMax < size + 8) :
    decodeAccepted size depth frameMax maxTableDepth = false := by
  simp [decodeAccepted]
  intro hsz
  exact absurd hsz (Nat.not_le_of_gt h)

def frameOverhead : Nat := 8
def wireSize (payload : Nat) : Nat := payload + 8

end NuropbRmq.Protocol
