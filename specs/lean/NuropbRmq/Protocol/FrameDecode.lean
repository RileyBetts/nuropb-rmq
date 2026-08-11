/-!
Bounded frame-decode acceptance predicate (Protocol invariant 6).
Mirrors SpeC++ `decode_accepted` and Python `frame.decode_frame` / table depth checks.
-/

namespace NuropbRmq.Protocol

/-- Decode is accepted iff length and nesting are within configured ceilings
    *before* treating the payload as valid (no allocation proportional to an
    unvalidated attacker-supplied length). -/
def decodeAccepted (size depth frameMax maxTableDepth : Nat) : Bool :=
  decide (size ≤ frameMax) && decide (depth ≤ maxTableDepth)

theorem decodeAccepted_implies_bounds
    (size depth frameMax maxTableDepth : Nat)
    (h : decodeAccepted size depth frameMax maxTableDepth = true) :
    size ≤ frameMax ∧ depth ≤ maxTableDepth := by
  simp [decodeAccepted, Bool.and_eq_true] at h
  exact h

theorem decodeAccepted_of_bounds
    (size depth frameMax maxTableDepth : Nat)
    (hs : size ≤ frameMax) (hd : depth ≤ maxTableDepth) :
    decodeAccepted size depth frameMax maxTableDepth = true := by
  simp [decodeAccepted, hs, hd]

theorem decodeAccepted_reject_oversize
    (size depth frameMax maxTableDepth : Nat)
    (h : frameMax < size) :
    decodeAccepted size depth frameMax maxTableDepth = false := by
  simp [decodeAccepted]
  intro hsz
  exact absurd hsz (Nat.not_le_of_gt h)

end NuropbRmq.Protocol
