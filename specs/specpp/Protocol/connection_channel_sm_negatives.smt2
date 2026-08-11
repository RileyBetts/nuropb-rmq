; Negative consistency checks: violating core Protocol invariants under the
; same axiom set must be UNSAT. Included axioms mirror the positive spec.
(set-logic ALL)
(set-info :status unsat)

(declare-datatypes () ((ConnState
  ConnInit ConnTcpConnected ConnTlsHandshaking ConnTlsVerified
  ConnStart ConnStartOk ConnTune ConnTuneOk ConnOpen ConnOpenOk
  ConnClosing ConnClosed ConnError)))

(declare-datatypes () ((ChanState
  ChanClosed ChanOpening ChanOpen ChanClosing ChanError)))

(declare-datatypes () ((TlsState TlsOff TlsHandshaking TlsVerified TlsFailed)))
(declare-datatypes () ((TlsProfile TlsVerifyFull TlsVerifyCustomSan TlsInsecureDevOnly)))
(declare-datatypes () ((SaslMech PLAIN EXTERNAL)))
(declare-datatypes () ((AmqpMethod
  ConnectionStartOk ConnectionTuneOk ConnectionOpen ConnectionClose
  ConnectionCloseOk ChannelOpen ChannelClose ChannelCloseOk
  QueueDeclare BasicPublish BasicConsume BasicAck)))

(declare-const frame_max Int)
(declare-const max_table_depth Int)
(declare-const heartbeat_timeout Int)
(declare-const tls_configured Bool)
(declare-const tls_profile TlsProfile)
(declare-const tls_state TlsState)
(declare-const conn_state ConnState)
(declare-const chan_state ChanState)
(declare-const sasl_over_verified_tls Bool)
(declare-const chosen_sasl SaslMech)
(declare-const broker_offers_external Bool)
(declare-const broker_offers_plain Bool)
(declare-const transition_rejected Bool)
(declare-const teardown_performed Bool)
(declare-const decode_size Int)
(declare-const decode_table_depth Int)
(declare-const decode_accepted Bool)
(declare-const amqp_negotiation_started Bool)
(declare-const method_to_send AmqpMethod)
(declare-const send_allowed Bool)

; --- Axioms (same as positive spec) ---
(assert (> frame_max 0))
(assert (<= frame_max 131072))
(assert (= max_table_depth 32))
(assert (and (> heartbeat_timeout 0) (<= heartbeat_timeout 60)))

(assert (= decode_accepted
  (and (<= decode_size frame_max)
       (>= decode_size 0)
       (<= decode_table_depth max_table_depth)
       (>= decode_table_depth 0))))

(assert (=> tls_configured
  (=> amqp_negotiation_started
    (or (= tls_state TlsVerified)
        (and (= tls_profile TlsInsecureDevOnly)
             (not (= tls_state TlsHandshaking))
             (not (= tls_state TlsOff))
             (not (= tls_state TlsFailed)))))))

(assert (=> (and tls_configured (= conn_state ConnStart))
  (or (= tls_state TlsVerified)
      (and (= tls_profile TlsInsecureDevOnly) (= tls_state TlsVerified)))))

(assert (=> tls_configured
  (= sasl_over_verified_tls (= tls_state TlsVerified))))
(assert (=> (and tls_configured (= conn_state ConnStartOk))
  sasl_over_verified_tls))

(assert (=> (= chosen_sasl EXTERNAL) broker_offers_external))
(assert (=> (= chosen_sasl PLAIN) broker_offers_plain))
(assert (or broker_offers_plain broker_offers_external))

(assert (=> transition_rejected teardown_performed))
(assert (=> (and transition_rejected teardown_performed)
  (or (= conn_state ConnError)
      (= conn_state ConnClosed)
      (= chan_state ChanError)
      (= chan_state ChanClosed))))

(define-fun legal_send ((m AmqpMethod) (cs ConnState) (chs ChanState)) Bool
  (or
    (and (= m ConnectionStartOk) (= cs ConnStart))
    (and (= m ConnectionTuneOk) (= cs ConnTune))
    (and (= m ConnectionOpen) (= cs ConnTuneOk))
    (and (= m ConnectionClose) (or (= cs ConnOpenOk) (= cs ConnOpen) (= cs ConnTuneOk)))
    (and (= m ConnectionCloseOk) (= cs ConnClosing))
    (and (= m ChannelOpen) (= cs ConnOpenOk) (= chs ChanClosed))
    (and (= m ChannelClose) (= chs ChanOpen) (= cs ConnOpenOk))
    (and (= m ChannelCloseOk) (= chs ChanClosing))
    (and (= m QueueDeclare) (= chs ChanOpen) (= cs ConnOpenOk))
    (and (= m BasicPublish) (= chs ChanOpen) (= cs ConnOpenOk))
    (and (= m BasicConsume) (= chs ChanOpen) (= cs ConnOpenOk))
    (and (= m BasicAck) (= chs ChanOpen) (= cs ConnOpenOk))))

(assert (= send_allowed (legal_send method_to_send conn_state chan_state)))

; --- Forced violations (should make the whole theory UNSAT) ---
; 1) Rejected transition without teardown
(assert transition_rejected)
(assert (not teardown_performed))

; 2) Also: oversized decode accepted (conflicts with decode_accepted definition)
(assert (= decode_size 999999))
(assert (= frame_max 131072))
(assert decode_accepted)

(check-sat)
(exit)
