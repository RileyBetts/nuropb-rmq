; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; Server request-id dedup: absent id is fresh. CheckSat must return sat.
(set-logic ALL)
(set-info :status sat)

(declare-datatypes () ((DedupOutcome Fresh Replay)))
(declare-const id_in_seen Bool)
(declare-const cap_off Bool)
(declare-const outcome DedupOutcome)

(assert (= outcome
  (ite id_in_seen Replay Fresh)))

(assert (not id_in_seen))
(assert (not cap_off))
(assert (= outcome Fresh))

(check-sat)
(get-model)
