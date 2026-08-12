; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; Connection blocked must not be silently ignored — expected sat
(set-logic ALL)
(declare-datatypes () ((BlockedState (Clear) (Blocked) (Seen))))
(declare-fun state () BlockedState)
(declare-fun handled () Bool)

; Legal: blocked frame observed ⇒ handled
(assert (= state Blocked))
(assert handled)
(assert (=> (= state Blocked) handled))
(check-sat)
