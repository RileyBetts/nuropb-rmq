; Negative Session correlation checks: violating Phase 1b invariants → UNSAT.
(set-logic ALL)
(set-info :status unsat)

(declare-const id_octet_len Int)
(declare-const id_charset_ok Bool)
(declare-const amqp_correlation_id Int)
(declare-const jsonrpc_id Int)
(declare-const dual_accessor_ok Bool)
(declare-const reply_queue_open Bool)
(declare-const id_outstanding Bool)
(declare-const table_nonempty Bool)

(declare-datatypes () ((RegisterOutcome
  RegOk RegInvalidId RegCollision RegReplyClosed)))
(declare-datatypes () ((ResolveOutcome
  FirstWin LateDiscarded UnknownId)))

(declare-const register_outcome RegisterOutcome)
(declare-const resolve_outcome ResolveOutcome)

(define-fun id_format_ok () Bool
  (and (>= id_octet_len 1)
       (<= id_octet_len 255)
       id_charset_ok))

(assert (= dual_accessor_ok (= amqp_correlation_id jsonrpc_id)))
(assert (=> table_nonempty reply_queue_open))
(assert (=> id_outstanding table_nonempty))

(assert (= register_outcome
  (ite (not reply_queue_open) RegReplyClosed
  (ite (not id_format_ok) RegInvalidId
  (ite id_outstanding RegCollision
       RegOk)))))

(assert (= resolve_outcome
  (ite id_outstanding FirstWin
       LateDiscarded)))

; --- Forced violations (each alone would be enough; assert all → unsat) ---

; 1) Dual-accessor divergence while claiming ok
(assert dual_accessor_ok)
(assert (not (= amqp_correlation_id jsonrpc_id)))

; 2) Pending entries with reply queue closed
(assert table_nonempty)
(assert (not reply_queue_open))

; 3) Collision accepted as RegOk
(assert reply_queue_open)
(assert id_format_ok)
(assert id_outstanding)
(assert (= register_outcome RegOk))

; 4) Late reply treated as FirstWin
(assert (not id_outstanding))
(assert (= resolve_outcome FirstWin))

(check-sat)
