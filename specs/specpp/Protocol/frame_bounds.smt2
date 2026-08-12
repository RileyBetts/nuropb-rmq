; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; Frame bounds: total wire size = payload + 8 ≤ frame_max
; SpeC++ CheckSat — expected sat
(set-logic ALL)
(define-fun frameOverhead () Int 8)
(define-fun wireSize ((p Int)) Int (+ p frameOverhead))
(define-fun encodeAccepted ((p Int) (fm Int)) Bool
  (and (>= fm frameOverhead) (<= (wireSize p) fm)))

(declare-const chunk Int)
(declare-const frameMax Int)
(assert (= frameMax 131072))
(assert (= chunk (- frameMax frameOverhead)))
(assert (encodeAccepted chunk frameMax))
(assert (not (encodeAccepted (+ chunk 1) frameMax)))
(check-sat)
