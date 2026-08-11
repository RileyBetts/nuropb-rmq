# Lean ↔ Python correspondence (Protocol + Session + Pattern)


Manual correspondence map for the Lean↔Python coupling decided in
`thinking/architecture.md`: SpeC++ → Lean model → property-based tests +
manual review. No code extraction.

## Alignment findings (2026-08-11)

Re-audit of SpeC++ / Lean / Python against this document.

| Area | Status | Notes |
|---|---|---|
| Protocol inv 1–7 | **Aligned** | State enums, `legalSend`, TLS-before-AMQP, reject→ERROR, frame bounds, heartbeat `1..60` match. Added `test_inv3_*` / `test_inv5_*`; transport validates/clamps heartbeat before SM. |
| Inv 7 vs watchdog | **Documented** | Lean models negotiate/store bounds only. Python `_heartbeat_loop` (send + 2× silence → `CONNECTION_LOST`) is the transport obligation under the same single-policy field — not a separate Lean event. |
| Session Phase 1b | **Aligned** | Id bounds/charset, collision reject, first-wins. Lean `replyOpen` is enforced at Session/RpcClient (`reply_queue_open`), not inside `CorrelationTable` alone. |
| Session Phase 2 | **Aligned** | Fail-fast clear pending, epoch bump, DLQ timeout synthesizer; mesh rebind caller-owned. |
| Pattern mesh/claims | **Aligned** | `inNamespace`/`tryBind` ↔ mesh guards; `tryAuth` ↔ `AuthConfig.verify_request`. Python also refuses empty method / `..` beyond SpeC++ prefix core. |
| Config SpeC++ | **SpeC++ only** | `specs/specpp/Config/queue_profile*.smt2` — durable↔`delivery_mode` consistency. **No Lean module** (deferred); intentional, not accidental drift. |
| TLS material / SASL EXTERNAL | **Outside Lean** | PEM sources + EXTERNAL selection are transport/config; Protocol Lean stops at TLS-verified before AMQP. |

Residual gaps (accepted): JWT crypto axiomatized in Lean; broker ACL external; queue-profile Lean deferred; heartbeat watchdog not reified as Lean events.

## Modules

| Lean | Python / SpeC++ |
|---|---|
| `NuropbRmq.Protocol.ConnState` | `nuropb_rmq.protocol.connection_sm.ConnState` |
| `NuropbRmq.Protocol.ChanState` | `nuropb_rmq.protocol.channel_sm.ChanState` |
| `NuropbRmq.Protocol.ConnectionSM` | `ConnectionStateMachine` + `ChannelStateMachine` |
| `NuropbRmq.Protocol.FrameDecode` | `nuropb_rmq.transport.frame` decode/encode bounds |
| `NuropbRmq.Protocol.Invariants` | SpeC++ invariants 1–7; PBTs under `tests/protocol/` + `tests/transport/` |
| `specs/specpp/Protocol/connection_channel_sm.smt2` | Same sort universe as Lean `ConnState` / `ChanState` / `TlsState` |
| `NuropbRmq.Session.Correlation` | `nuropb_rmq.session.{ids,correlation,session}` |
| `NuropbRmq.Session.Invariants` | SpeC++ Session Phase 1b; PBTs under `tests/session/` |
| `NuropbRmq.Session.DeadLetterTimeout` | Broker TTL/DLX + `patterns/dlq_timeout.py` |
| `NuropbRmq.Session.Reconnect` | `session/reconnect.py` + `Session.reconnect` |
| `NuropbRmq.Session.Phase2Invariants` | SpeC++ Phase 2; PBTs under `tests/session/test_reconnect.py` |
| `NuropbRmq.Pattern.Mesh` | `nuropb_rmq.patterns.mesh` |
| `NuropbRmq.Pattern.Claims` | `nuropb_rmq.patterns.context` |
| `NuropbRmq.Pattern.Invariants` | SpeC++ Pattern; PBTs under `tests/patterns/` |
| `specs/specpp/Session/correlation.smt2` | Session correlation sorts / clauses |
| `specs/specpp/Session/phase2_reconnect.smt2` | Phase 2 terminal-state / reconnect epoch clauses |
| `specs/specpp/Pattern/mesh_claims.smt2` | Pattern mesh/claims sorts / clauses |
| `specs/specpp/Config/queue_profile.smt2` | Python `config/queue_profile.py` (SpeC++ only; Lean deferred) |

## States

| Lean `ConnState` | Python `ConnState` |
|---|---|
| `init` | `INIT` |
| `tcpConnected` | `TCP_CONNECTED` |
| `tlsHandshaking` | `TLS_HANDSHAKING` |
| `tlsVerified` | `TLS_VERIFIED` |
| `start` | `START` |
| `startOk` | `START_OK` |
| `tune` | `TUNE` |
| `tuneOk` | `TUNE_OK` |
| `open` | `OPEN` |
| `openOk` | `OPEN_OK` |
| `closing` | `CLOSING` |
| `closed` | `CLOSED` |
| `error` | `ERROR` |

| Lean `ChanState` | Python `ChanState` |
|---|---|
| `closed` | `CLOSED` |
| `opening` | `OPENING` |
| `open` | `OPEN` |
| `closing` | `CLOSING` |
| `error` | `ERROR` |

## Events / methods

| Lean `Event` | Python SM method |
|---|---|
| `tcpConnected useTls` | `on_tcp_connected(tls=…)` |
| `tlsVerified` | `on_tls_verified()` |
| `amqpHeader` | `allow_amqp_header()` |
| `connStart` | `on_connection_start()` |
| `startOk` | `on_connection_start_ok_sent()` |
| `tune` | `on_connection_tune()` |
| `tuneOk hb` | `on_connection_tune_ok_sent(heartbeat=hb)` |
| `open` | `on_connection_open_sent()` |
| `openOk` | `on_connection_open_ok()` |
| `beginClose` | `begin_close()` |
| `closeOk` | `on_close_ok()` |
| `reject` / `tryStep = none` | `reject(reason)` → `ERROR` |

| Lean `ConnMethod` / `legalSend` | Python |
|---|---|
| `legalSend .startOk .start` | `assert_can_send_connection_method(CONNECTION_START_OK)` in `START` |
| `legalSend .tuneOk .tune` | `CONNECTION_TUNE_OK` in `TUNE` |
| `legalSend .open .tuneOk` | `CONNECTION_OPEN` in `TUNE_OK` |
| `legalSend .closeOk .closing` | `CONNECTION_CLOSE_OK` in `CLOSING` |

## Protocol invariants

| # | Lean theorem(s) | Python / tests |
|---|---|---|
| 1 | `legalSend_*`, `tryStep_startOk_requires_legal` | `assert_can_send_connection_method`; `test_inv1_*`, `test_illegal_method_send_rejected` |
| 2 | `amqpHeader_rejects_during_tls_handshake`, `connStart_requires_verified_tls` | `allow_amqp_header`; `test_inv2_*`, `test_tls_required_before_amqp` |
| 3 | `startOk_requires_verified_tls` | TLS path only via `on_tls_verified` before START; `test_inv3_start_ok_after_verified_tls` |
| 4 | `reject_implies_error`, `reject_event_tears_down` | `reject` → `ERROR`; `test_inv4_*` |
| 5 | `close_reachable_all`, `beginClose_ok_from_openOk` | `begin_close` from non-terminal; `test_inv5_*` |
| 6 | `decodeAccepted_*`, `inv6_decodeAccepted_implies_bounds` | `decode_frame` / `encode_table`; `test_inv6_pbt_*` |
| 7 | `tuneOk_heartbeat_bounds`, `plainOpenOk_heartbeat` | SM `1..60`; `AmqpConnection.connect` validates config + clamps; `test_inv7_*`; watchdog in `tests/transport/test_heartbeat.py` |

## Session Phase 1b

| SpeC++ / Lean | Python |
|---|---|
| `validIdLen` / `validIdLen_bounds` | `session.ids.validate_id` (1..255 octets + charset) |
| `dualAccessorOk` | RpcClient sets AMQP `correlation_id` = JSON-RPC `id` |
| `tryRegister` → `.collision` | `CorrelationTable.register` → `IdCollisionError` |
| `tryRegister` → `.replyClosed` | `RpcClient.request` requires `session.reply_queue_open` |
| `tryResolve` → `.firstWin` / `.lateDiscard` | `CorrelationTable.resolve` first-wins / late discard |
| `openReply` / `closeReply` brackets `pending` | `Session.start` / `Session.close` + `discard_all` |
| `wellFormed` | reply queue lifetime brackets correlation table |

| Lean theorem(s) | Python / tests |
|---|---|
| `register_collision`, `register_ok_fresh` | `test_collision_reject`, `test_pbt_collision_reject` |
| `resolve_first_wins`, `second_resolve_is_late` | `test_first_reply_wins_late_discarded`, `test_pbt_first_wins` |
| `register_requires_reply_open`, `close_clears_pending` | Session start/close; RpcClient gate; loss → `discard_all` |

## Pattern (Mesh + Claims) — SpeC++ + Lean + Python

| Lean / SpeC++ | Python |
|---|---|
| `NuropbRmq.Pattern.Mesh.inNamespace` / `tryBind` | `ServiceIdentity.assert_in_namespace` / `MeshService.assert_bind_allowed` |
| `BindOk` / `BindRefused` | allow / `BIND_REFUSED` / `NamespaceError` |
| `NuropbRmq.Pattern.Claims.tryAuth` | `AuthConfig.verify_request` |
| `AuthPublicSkip` | `AuthConfig.public_methods` → verify returns `None` |
| `AuthReject` fail-closed | missing/expired/unbound/bad-sig → `CLAIMS_*` / `UNAUTHORIZED` |
| `AuthOk` (`jti`/`method` bind) | `jti`↔corr, `method` claim (constant-time compare in Python) |
| `specs/specpp/Pattern/mesh_claims.smt2` | PBTs under `tests/patterns/test_mesh.py` + `test_context.py` |

| Lean theorem(s) | Python / tests |
|---|---|
| `tryBind_ok_of_inNamespace`, `tryBind_refused_*`, `tryBind_exact_service` | `test_namespace_refuse`, `test_pbt_routing_key_in_namespace`, `test_pbt_exact_service_key` |
| `tryAuth_public_skip` | `test_public_method_skips_claims`, `test_pbt_public_skip` |
| `tryAuth_reject_*`, `tryAuth_ok` | `test_missing_claims_*`, `test_pbt_jti_must_match` |

JWT crypto (`validSig` / `expired`) is axiomatized in Lean; broker ACL remains an external axiom. Python also refuses empty method / `..` segments beyond the SpeC++ prefix core.

## Session Phase 2 (Reconnect + DeadLetterTimeout)

| Lean / SpeC++ | Python |
|---|---|
| `exclusiveFate` / TTL vs ack | Broker TTL/DLX authoritative; DLQ timeout synthesizer |
| `terminalOf` acked / dlqTimeout / connectionLost | RPC result, DLQ `REQUEST_TIMEOUT`, `CONNECTION_LOST` |
| `onDisconnect` clears pending | `Session._on_connection_lost` / `correlation.discard_all` |
| `onReconnect` bumps epoch | `Session.reconnect` / `ReconnectCoordinator` |
| `MeshService.rebind` | Fresh connection + namespaced binds; caller restarts `RpcServer` |
| `specs/specpp/Session/phase2_reconnect.smt2` | `tests/session/test_reconnect.py` + integration |

## Config (SpeC++ only)

| SpeC++ | Python | Lean |
|---|---|---|
| `Config/queue_profile.smt2` (sat) | `QueueProfile` durable ⇒ `delivery_mode=2` | **Deferred** |
| `Config/queue_profile_negatives.smt2` (unsat) | publish refuse non-persistent on durable | **Deferred** |

## Build / test

```bash
python specs/specpp/check_sat.py
cd specs/lean && lake build
cd ../.. && pytest -q tests/protocol tests/transport tests/session tests/patterns
# claims unit tests need: pip install -e ".[claims]"
# integration (needs local RabbitMQ):
pytest -q tests/integration
```
