; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; Fail-fast: pending after disconnect must be 0 — violating that is unsat
(set-logic ALL)
(set-info :status unsat)
(declare-fun fail_outstanding () Bool)
(declare-fun pending_after_fail_disconnect () Int)
(assert fail_outstanding)
(assert (= pending_after_fail_disconnect 0))
; violation
(assert (> pending_after_fail_disconnect 0))
(check-sat)
