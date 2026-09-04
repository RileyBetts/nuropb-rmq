; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; Replay of a seen id cannot be Fresh — unsat
(set-logic ALL)
(set-info :status unsat)

(declare-datatypes () ((DedupOutcome Fresh Replay)))
(declare-const id_in_seen Bool)
(declare-const outcome DedupOutcome)

(assert (= outcome
  (ite id_in_seen Replay Fresh)))

(assert id_in_seen)
(assert (= outcome Fresh))

(check-sat)
