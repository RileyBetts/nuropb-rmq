; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; SpeC++ Phase 2: request terminal states + reconnect epoch.
; CheckSat must return sat.
(set-logic ALL)
(set-info :status sat)

(declare-datatypes () ((Terminal
  TermAckedWithResponse
  TermDlqTimeoutSynthesized
  TermConnectionLost
  TermNone)))

(declare-datatypes () ((Arrival
  ArrReply
  ArrDupReply
  ArrTimeout
  ArrNone)))

(declare-const in_request_queue Bool)
(declare-const ttl_expired Bool)
(declare-const service_acked Bool)
(declare-const timeout_synthesized Bool)
(declare-const terminal Terminal)
(declare-const first_arrival Arrival)
(declare-const second_arrival Arrival)
(declare-const first_wins Bool)
(declare-const reply_queue_open Bool)
(declare-const table_nonempty Bool)
(declare-const epoch Int)
(declare-const after_reconnect_epoch Int)
(declare-const after_reconnect_table_nonempty Bool)
(declare-const after_reconnect_reply_open Bool)

; Mutual exclusivity: TTL dead-letter vs successful service processing
(assert (not (and ttl_expired service_acked)))

; Terminal assignment
(assert (= terminal
  (ite service_acked TermAckedWithResponse
  (ite (and ttl_expired timeout_synthesized) TermDlqTimeoutSynthesized
  (ite (not reply_queue_open) TermConnectionLost
       TermNone)))))

; TTL bounds: cannot remain in queue forever once TTL fires
(assert (=> (and in_request_queue ttl_expired)
            (or timeout_synthesized (not in_request_queue))))

; First-reply-wins
(assert (= first_wins
  (or (= second_arrival ArrNone)
      (distinct first_arrival ArrNone))))
(assert (=> (and (= first_arrival ArrReply) (= second_arrival ArrTimeout)) first_wins))
(assert (=> (and (= first_arrival ArrTimeout) (= second_arrival ArrReply)) first_wins))

; Reply queue brackets correlation table
(assert (=> table_nonempty reply_queue_open))

; Reconnect epoch: old outstanding cleared; new reply queue brackets new table
(assert (= after_reconnect_epoch (+ epoch 1)))
(assert (not after_reconnect_table_nonempty))
(assert after_reconnect_reply_open)
(assert (=> after_reconnect_table_nonempty after_reconnect_reply_open))

; Positive model
(assert (not ttl_expired))
(assert service_acked)
(assert (= terminal TermAckedWithResponse))
(assert (= first_arrival ArrReply))
(assert (= second_arrival ArrDupReply))
(assert first_wins)
(assert reply_queue_open)
(assert (not table_nonempty))
(assert (= epoch 0))
(assert (= after_reconnect_epoch 1))
(assert after_reconnect_reply_open)
(assert (not after_reconnect_table_nonempty))

(check-sat)
(get-model)
