; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; Connection blocked silent-drop negative — expected unsat
(set-logic ALL)
(declare-datatypes () ((BlockedState (Clear) (Blocked))))
(declare-fun state () BlockedState)
(declare-fun handled () Bool)
(assert (= state Blocked))
(assert (not handled))
(assert (=> (= state Blocked) handled))
(check-sat)
