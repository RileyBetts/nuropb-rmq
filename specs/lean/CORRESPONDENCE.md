# Lean ↔ Python correspondence (Protocol Phase 1 + Session Phase 1b)

Manual correspondence map for the Lean↔Python coupling decided in
`thinking/architecture.md`: SpeC++ → Lean model → property-based tests +
manual review. No code extraction.

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
| `specs/specpp/Session/correlation.smt2` | Session correlation sorts / clauses |

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
| 1 | `legalSend_*`, `tryStep_startOk_requires_legal` | `assert_can_send_connection_method`; `test_inv1_*` |
| 2 | `amqpHeader_rejects_during_tls_handshake`, `connStart_requires_verified_tls`, `tls_skip_verify_errors` | `allow_amqp_header`; `test_inv2_*` |
| 3 | `startOk_requires_verified_tls` | start-ok path only after TLS verified when TLS configured |
| 4 | `reject_implies_error`, `reject_event_tears_down` | `reject` → `ERROR`; `test_inv4_*` |
| 5 | `close_reachable_all`, `beginClose_ok_from_openOk` | `begin_close` from non-terminal |
| 6 | `decodeAccepted_*`, `inv6_decodeAccepted_implies_bounds` | `decode_frame` / `encode_table`; `test_inv6_pbt_*` |
| 7 | `tuneOk_heartbeat_bounds`, `plainOpenOk_heartbeat` | heartbeat `1..60`; `test_inv7_*` |

## Session Phase 1b

| SpeC++ / Lean | Python |
|---|---|
| `validIdLen` / `validIdLen_bounds` | `session.ids.validate_id` (1..255 octets + charset) |
| `dualAccessorOk` | RpcClient sets AMQP `correlation_id` = JSON-RPC `id` |
| `tryRegister` → `.collision` | `CorrelationTable.register` → `IdCollisionError` |
| `tryResolve` → `.firstWin` / `.lateDiscard` | `CorrelationTable.resolve` first-wins / late discard |
| `openReply` / `closeReply` brackets `pending` | `Session.start` / `Session.close` + `discard_all` |
| `wellFormed` | reply queue lifetime brackets correlation table |

| Lean theorem(s) | Python / tests |
|---|---|
| `register_collision`, `register_ok_fresh` | `test_collision_reject`, `test_pbt_collision_reject` |
| `resolve_first_wins`, `second_resolve_is_late` | `test_first_reply_wins_late_discarded`, `test_pbt_first_wins` |
| `register_requires_reply_open`, `close_clears_pending` | Session start/close; reply queue exclusive auto-delete |

## Build / test

```bash
python specs/specpp/check_sat.py
cd specs/lean && lake build
cd ../.. && pytest -q tests/protocol tests/transport tests/session tests/patterns
# integration (needs local RabbitMQ):
pytest -q tests/integration
```
