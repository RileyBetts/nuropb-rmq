# Lean ↔ Python correspondence (Protocol Phase 1)

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

## Invariants

| # | Lean theorem(s) | Python / tests |
|---|---|---|
| 1 | `legalSend_*`, `tryStep_startOk_requires_legal` | `assert_can_send_connection_method`; `test_inv1_*` |
| 2 | `amqpHeader_rejects_during_tls_handshake`, `connStart_requires_verified_tls`, `tls_skip_verify_errors` | `allow_amqp_header`; `test_inv2_*` |
| 3 | `startOk_requires_verified_tls` | start-ok path only after TLS verified when TLS configured |
| 4 | `reject_implies_error`, `reject_event_tears_down` | `reject` → `ERROR`; `test_inv4_*` |
| 5 | `close_reachable_all`, `beginClose_ok_from_openOk` | `begin_close` from non-terminal |
| 6 | `decodeAccepted_*`, `inv6_decodeAccepted_implies_bounds` | `decode_frame` / `encode_table`; `test_inv6_pbt_*` |
| 7 | `tuneOk_heartbeat_bounds`, `plainOpenOk_heartbeat` | heartbeat `1..60`; `test_inv7_*` |

## Build / test

```bash
cd specs/lean && lake build
cd ../.. && pytest -q tests/protocol tests/transport
```
