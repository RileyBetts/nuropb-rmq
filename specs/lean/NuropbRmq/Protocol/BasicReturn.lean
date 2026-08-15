/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

/-!
`basic.return` is distinct from publisher confirms (SpeC++ basic_return.smt2).

Confirms answer whether the broker accepted the message; return answers
whether it was routable. A mandatory unroutable publish produces a return
without changing a DLQ drop outcome.
-/

namespace NuropbRmq.Protocol

inductive PublishSignal where
  | confirmAck
  | confirmNack
  | basicReturn
  deriving DecidableEq, Repr

/-- Return and nack are different signals — never conflate them. -/
theorem return_ne_nack : PublishSignal.basicReturn ≠ PublishSignal.confirmNack := by
  intro h; cases h

theorem return_ne_ack : PublishSignal.basicReturn ≠ PublishSignal.confirmAck := by
  intro h; cases h

/-- Mandatory + unroutable ⇒ `basic.return`. Non-mandatory unroutable is silent. -/
def mandatoryUnroutable (mandatory routable : Bool) : Option PublishSignal :=
  if mandatory && !routable then some .basicReturn else none

theorem mandatory_unroutable_returns :
    mandatoryUnroutable true false = some PublishSignal.basicReturn := rfl

theorem optional_unroutable_silent :
    mandatoryUnroutable false false = none := rfl

theorem mandatory_routable_no_return :
    mandatoryUnroutable true true = none := rfl

/-- Observability only: a return does not rewrite a DLQ drop into a different fate. -/
def dropUnchanged (dropped : Bool) (_returned : Bool) : Bool :=
  dropped

theorem return_does_not_undrop (returned : Bool) :
    dropUnchanged true returned = true := rfl

end NuropbRmq.Protocol
