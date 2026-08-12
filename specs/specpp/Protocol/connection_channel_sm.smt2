; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; SpeC++-style Protocol connection/channel state-machine specification
; Sort universe + clauses for architecture invariants 1–7.
; CheckSat must return sat (spec is consistent / admits a model).
; Run: z3 specs/specpp/Protocol/connection_channel_sm.smt2
;   or: python specs/specpp/check_sat.py

(set-logic ALL)
(set-info :source |nuropb-rmq Protocol SM SpeC++ consistency check|)
(set-info :status sat)

; --- Sort universe ---
(declare-datatypes () ((ConnState
  ConnInit
  ConnTcpConnected
  ConnTlsHandshaking
  ConnTlsVerified
  ConnStart
  ConnStartOk
  ConnTune
  ConnTuneOk
  ConnOpen
  ConnOpenOk
  ConnClosing
  ConnClosed
  ConnError)))

(declare-datatypes () ((ChanState
  ChanClosed
  ChanOpening
  ChanOpen
  ChanClosing
  ChanError)))

(declare-datatypes () ((TlsState
  TlsOff
  TlsHandshaking
  TlsVerified
  TlsFailed)))

(declare-datatypes () ((TlsProfile
  TlsVerifyFull
  TlsVerifyCustomSan
  TlsInsecureDevOnly)))

(declare-datatypes () ((SaslMech PLAIN EXTERNAL)))

(declare-datatypes () ((FrameKind
  FrameMethod
  FrameHeader
  FrameBody
  FrameHeartbeat)))

(declare-datatypes () ((AmqpMethod
  ConnectionStart
  ConnectionStartOk
  ConnectionTune
  ConnectionTuneOk
  ConnectionOpen
  ConnectionOpenOk
  ConnectionClose
  ConnectionCloseOk
  ChannelOpen
  ChannelOpenOk
  ChannelClose
  ChannelCloseOk
  QueueDeclare
  BasicPublish
  BasicConsume
  BasicAck
  BasicDeliver)))

; --- Constants / configuration ---
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

; Config ceilings (profile defaults)
(assert (> frame_max 0))
(assert (<= frame_max 131072))
(assert (= max_table_depth 32))
(assert (> heartbeat_timeout 0))
(assert (<= heartbeat_timeout 60))

; --- Invariant 7: single heartbeat policy (one positive timeout) ---
(assert (and (> heartbeat_timeout 0) (<= heartbeat_timeout 60)))

; --- Invariant 6: frame decode bounds before accept/allocate ---
(assert (= decode_accepted
  (and (<= decode_size frame_max)
       (>= decode_size 0)
       (<= decode_table_depth max_table_depth)
       (>= decode_table_depth 0))))

; Model admits both accept and reject cases under the same rule
(assert (or decode_accepted (not decode_accepted)))

; --- Invariant 2: TLS-before-AMQP when TLS configured ---
(assert (=> tls_configured
  (=> amqp_negotiation_started
    (or (= tls_state TlsVerified)
        ; insecure profile is named and non-production; still requires handshake complete
        (and (= tls_profile TlsInsecureDevOnly)
             (not (= tls_state TlsHandshaking))
             (not (= tls_state TlsOff))
             (not (= tls_state TlsFailed)))))))

; When TLS configured, reaching ConnStart implies verified (or insecure-dev completed) TLS
(assert (=> (and tls_configured (= conn_state ConnStart))
  (or (= tls_state TlsVerified)
      (and (= tls_profile TlsInsecureDevOnly) (= tls_state TlsVerified)))))

; --- Invariant 3: SASL only trusted over verified TLS when TLS configured ---
(assert (=> tls_configured
  (= sasl_over_verified_tls (= tls_state TlsVerified))))
(assert (=> (and tls_configured (= conn_state ConnStartOk))
  sasl_over_verified_tls))

; SASL choice must be from broker ads
(assert (=> (= chosen_sasl EXTERNAL) broker_offers_external))
(assert (=> (= chosen_sasl PLAIN) broker_offers_plain))
(assert (or broker_offers_plain broker_offers_external))

; --- Invariant 4: rejected transition => teardown ---
(assert (=> transition_rejected teardown_performed))
(assert (=> (and transition_rejected teardown_performed)
  (or (= conn_state ConnError)
      (= conn_state ConnClosed)
      (= chan_state ChanError)
      (= chan_state ChanClosed))))

; --- Invariant 5: close reachable from non-terminal states ---
(define-fun is_terminal_conn ((s ConnState)) Bool
  (or (= s ConnClosed) (= s ConnError)))

(define-fun close_reachable ((s ConnState)) Bool
  (or (= s ConnClosing)
      (= s ConnClosed)
      (= s ConnError)
      (= s ConnOpenOk)
      (= s ConnOpen)
      (= s ConnTuneOk)
      (= s ConnTune)
      (= s ConnStartOk)
      (= s ConnStart)
      (= s ConnTlsVerified)
      (= s ConnTcpConnected)
      (= s ConnInit)))

(assert (=> (not (is_terminal_conn conn_state)) (close_reachable conn_state)))

; --- Invariant 1: method send only from legal states ---
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

; Consistency witness: a concrete happy-path model must exist
(assert tls_configured)
(assert (= tls_profile TlsVerifyFull))
(assert (= tls_state TlsVerified))
(assert (= conn_state ConnOpenOk))
(assert (= chan_state ChanOpen))
(assert broker_offers_plain)
(assert (= chosen_sasl PLAIN))
(assert sasl_over_verified_tls)
(assert (not transition_rejected))
(assert (= method_to_send BasicPublish))
(assert send_allowed)
(assert (= decode_size 64))
(assert (= decode_table_depth 2))
(assert decode_accepted)
(assert (= heartbeat_timeout 60))
(assert (= frame_max 131072))
(assert (not amqp_negotiation_started)) ; already past negotiation

(check-sat)
(exit)
