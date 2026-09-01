; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; One miss is not lost — claiming lost at missed=1 is unsat
(set-logic ALL)
(set-info :status unsat)
(declare-fun missed () Int)
(declare-fun lost () Bool)
(assert (= missed 1))
(assert (= lost (>= missed 2)))
(assert lost)
(check-sat)
