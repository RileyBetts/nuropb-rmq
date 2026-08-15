; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; basic.return vs publisher confirms — expected sat
; Confirms answer "did the broker take it"; return answers "was it routable".
(set-logic ALL)
(declare-datatypes () ((PublishSignal (ConfirmAck) (ConfirmNack) (BasicReturn))))

(declare-fun mandatory () Bool)
(declare-fun routable () Bool)
(declare-fun confirmMode () Bool)
(declare-fun signal () PublishSignal)

; Mandatory + unroutable produces BasicReturn (not ConfirmNack)
(assert mandatory)
(assert (not routable))
(assert (= signal BasicReturn))
(assert (distinct signal ConfirmNack))
(assert (distinct signal ConfirmAck))

; In confirm mode the broker may still ack after returning; signals remain distinct
(assert confirmMode)

(check-sat)
