/-!
Publisher confirm invariants (SpeC++ publisher_confirms.smt2).
-/

namespace NuropbRmq.Protocol

inductive ConfirmOutcome where
  | pending
  | ack
  | nack
  deriving DecidableEq, Repr

def complete (o : ConfirmOutcome) : Bool :=
  match o with
  | .ack | .nack => true
  | .pending => false

/-- In confirm mode, a completed publish is never still pending. -/
theorem complete_not_pending (o : ConfirmOutcome) (h : complete o = true) :
    o ≠ ConfirmOutcome.pending := by
  cases o <;> simp [complete] at h <;> try contradiction
  all_goals intro hneq; cases hneq

/-- Multiple ack covers all tags ≤ deliveryTag that are outstanding. -/
def multipleCovers (deliveryTag tag : Nat) : Bool :=
  decide (tag ≤ deliveryTag)

theorem multipleCovers_le (deliveryTag tag : Nat)
    (h : multipleCovers deliveryTag tag = true) : tag ≤ deliveryTag := by
  simpa [multipleCovers] using h

end NuropbRmq.Protocol
