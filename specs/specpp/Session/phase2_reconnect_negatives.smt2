; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; Negative Phase 2: forced invariant violations → UNSAT
(set-logic ALL)
(set-info :status unsat)

(declare-datatypes () ((Terminal
  TermAckedWithResponse TermDlqTimeoutSynthesized TermConnectionLost TermNone)))
(declare-datatypes () ((Arrival ArrReply ArrDupReply ArrTimeout ArrNone)))

(declare-const ttl_expired Bool)
(declare-const service_acked Bool)
(declare-const timeout_synthesized Bool)
(declare-const terminal Terminal)
(declare-const reply_queue_open Bool)
(declare-const table_nonempty Bool)
(declare-const after_reconnect_table_nonempty Bool)
(declare-const after_reconnect_reply_open Bool)

(assert (not (and ttl_expired service_acked)))

(assert (= terminal
  (ite service_acked TermAckedWithResponse
  (ite (and ttl_expired timeout_synthesized) TermDlqTimeoutSynthesized
  (ite (not reply_queue_open) TermConnectionLost
       TermNone)))))

(assert (=> table_nonempty reply_queue_open))
(assert (=> after_reconnect_table_nonempty after_reconnect_reply_open))

; Violations
(assert ttl_expired)
(assert service_acked)

(assert table_nonempty)
(assert (not reply_queue_open))

(assert after_reconnect_table_nonempty)
(assert (not after_reconnect_reply_open))

(check-sat)
