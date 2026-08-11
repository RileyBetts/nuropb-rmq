; SpeC++ Session correlation specification (Phase 1b).
; Id format, dual-accessor consistency, collision reject, first-reply-wins,
; reply-queue lifetime brackets correlation table.
; CheckSat must return sat.
; Run: z3 specs/specpp/Session/correlation.smt2
;   or: python specs/specpp/check_sat.py

(set-logic ALL)
(set-info :source |nuropb-rmq Session correlation SpeC++ consistency check|)
(set-info :status sat)

; --- Sort universe ---
(declare-datatypes () ((CorrAction
  OpenReplyQueue
  CloseReplyQueue
  Register
  Resolve
  LateDiscard)))

(declare-datatypes () ((RegisterOutcome
  RegOk
  RegInvalidId
  RegCollision
  RegReplyClosed)))

(declare-datatypes () ((ResolveOutcome
  FirstWin
  LateDiscarded
  UnknownId)))

; --- Configuration / message fields ---
(declare-const id_octet_len Int)
(declare-const id_charset_ok Bool)
(declare-const amqp_correlation_id Int) ; abstract id token
(declare-const jsonrpc_id Int)
(declare-const dual_accessor_ok Bool)

(declare-const reply_queue_open Bool)
(declare-const id_outstanding Bool)      ; id currently in correlation table
(declare-const table_nonempty Bool)

(declare-const action CorrAction)
(declare-const register_outcome RegisterOutcome)
(declare-const resolve_outcome ResolveOutcome)

; --- Id format (AMQP shortstr ∩ JSON-RPC string discipline) ---
(define-fun id_format_ok () Bool
  (and (>= id_octet_len 1)
       (<= id_octet_len 255)
       id_charset_ok))

; Dual-accessor: one Session value in both places
(assert (= dual_accessor_ok (= amqp_correlation_id jsonrpc_id)))

; Well-formed Session invariant: pending entries only while reply queue open
(assert (=> table_nonempty reply_queue_open))
(assert (=> id_outstanding table_nonempty))

; Register outcomes
(assert (= register_outcome
  (ite (not reply_queue_open) RegReplyClosed
  (ite (not id_format_ok) RegInvalidId
  (ite id_outstanding RegCollision
       RegOk)))))

; Resolve outcomes (first-reply-wins)
(assert (= resolve_outcome
  (ite id_outstanding FirstWin
       LateDiscarded)))

; --- Positive model constraints (admitting a concrete good world) ---
; A valid open session can register a fresh well-formed id and resolve once.
(assert reply_queue_open)
(assert id_format_ok)
(assert dual_accessor_ok)
(assert (not id_outstanding))  ; fresh id → register ok, then we model resolve separately
(assert (= register_outcome RegOk))

; After a successful first resolve of an outstanding id:
(declare-const after_first_resolve ResolveOutcome)
(assert (= after_first_resolve
  (ite true FirstWin LateDiscarded))) ; id was outstanding at resolve time
(assert (= after_first_resolve FirstWin))

; Close brackets: closing reply queue empties the table
(declare-const after_close_table_nonempty Bool)
(declare-const after_close_reply_open Bool)
(assert (=> (not after_close_reply_open) (not after_close_table_nonempty)))

(check-sat)
(get-model)
