/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

/-!
Consumer delivery settlement: exactly one of ack / nack / reject per tag.
-/

namespace NuropbRmq.Protocol

inductive SettleKind where
  | ack
  | nack
  | reject
  deriving DecidableEq, Repr

/-- A delivery tag is settled at most once (client obligation). -/
def settleOnce (settled : Bool) (_attempt : SettleKind) : Bool :=
  !settled

theorem settleOnce_requires_unset (_attempt : SettleKind)
    (h : settleOnce true _attempt = true) : False := by
  simp [settleOnce] at h

theorem settleOnce_ok_when_open (_attempt : SettleKind) :
    settleOnce false _attempt = true := by
  simp [settleOnce]

end NuropbRmq.Protocol
