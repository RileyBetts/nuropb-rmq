; Frame bounds negatives — expected unsat
; Claim: payload whose wire size (payload+8) exceeds frame_max is accepted.
(set-logic ALL)
(define-fun frameOverhead () Int 8)
(define-fun wireSize ((p Int)) Int (+ p frameOverhead))
(define-fun encodeAccepted ((p Int) (fm Int)) Bool
  (and (>= fm frameOverhead) (<= (wireSize p) fm)))

(declare-const payload Int)
(declare-const frameMax Int)
(assert (= frameMax 131072))
(assert (= payload 131072))
(assert (encodeAccepted payload frameMax))
(check-sat)
