; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; basic.return negatives — expected unsat
; Illegal: conflate BasicReturn with ConfirmNack
(set-logic ALL)
(declare-datatypes () ((PublishSignal (ConfirmAck) (ConfirmNack) (BasicReturn))))
(declare-fun signal () PublishSignal)

(assert (= signal BasicReturn))
(assert (= signal ConfirmNack))
(check-sat)
