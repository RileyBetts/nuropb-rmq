; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; Publisher confirms negatives — expected unsat
(set-logic ALL)
(declare-datatypes () ((Outcome (Ack) (Nack) (Pending))))
(declare-fun outstanding (Int) Outcome)
(declare-fun confirmMode () Bool)
(define-fun complete ((t Int)) Bool
  (or (= (outstanding t) Ack) (= (outstanding t) Nack)))

; Illegal: claim complete while still Pending
(assert confirmMode)
(assert (= (outstanding 1) Pending))
(assert (complete 1))
(check-sat)
