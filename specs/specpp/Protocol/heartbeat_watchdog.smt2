; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; Two missed peer heartbeats ⇒ connection lost — sat
(set-logic ALL)
(declare-fun missed () Int)
(declare-fun lost () Bool)
(assert (= missed 2))
(assert (= lost (>= missed 2)))
(assert lost)
(check-sat)
