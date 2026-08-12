; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; SpeC++ Config: durable queue never disagrees with persistent delivery_mode.
; CheckSat must return sat.
(set-logic ALL)
(set-info :status sat)

(declare-const durable Bool)
(declare-const delivery_mode Int)
(declare-const consistent Bool)

; delivery_mode: 1 = non-persistent, 2 = persistent
(define-fun profile_ok () Bool
  (and (or (= delivery_mode 1) (= delivery_mode 2))
       (= consistent
          (and (=> durable (= delivery_mode 2))
               (=> (not durable) (= delivery_mode 1))))))

(assert profile_ok)
(assert durable)
(assert (= delivery_mode 2))
(assert consistent)

(check-sat)
(get-model)
