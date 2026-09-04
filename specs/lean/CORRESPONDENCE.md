# Lean ↔ Python correspondence (Protocol + Session + Pattern)


Manual correspondence map for the Lean↔Python coupling: SpeC++ → Lean model →
property-based tests + manual review. No code extraction.

## Alignment findings (2026-09-04)

Re-audit of SpeC++ / Lean / Python against this document after the Lean
client Transport split and coverage smokes.

| Area | Status | Notes |
|---|---|---|
| Protocol inv 1–7 | **Aligned** | Includes `legalSend updateSecret` (OPEN_OK only), `publishAllowed` while blocked, heartbeat miss-count event (2× → ERROR). Channel `allowsOps` / `Reachable` witnesses in Lean. |
| Inv 7 vs watchdog | **Aligned** | Lean `heartbeatPeer` miss count; Python `_heartbeat_loop` still owns wall-clock. |
| Session Phase 1b | **Aligned** | First-wins / reply-open register gate; Lean `Ids.validId` charset theorems (Python `validate_id`). |
| Session Phase 2 | **Aligned** | Fail-fast `onDisconnect` clears pending; `onDisconnectPark` + `wellFormedPark` (pending may survive the reply-queue gap); `onReconnect` keeps count. |
| Pattern mesh/claims | **Aligned** | `tryAuth` decision tree plus executable HS256 `Pattern.Jwt.verifyHs256` and opaque `authorizeOk` / Lean IO `AuthConfig.authorize`. Lean IO claims smoke uses `goldenToken` plus deny/allow. |
| Pattern ACL | **Aligned** | `Pattern.Acl` prefix profiles; Python `patterns/acl.py`; CI management-API test. |
| Config SpeC++ | **Aligned** | Unchanged. |
| Lean IO runtime | **Aligned** | `NuropbRMQ.connect` / `connectWith` + `Transport`; `expectMethod` queues `BASIC_DELIVER`. Coverage: `./scripts/smoke_lean_coverage.sh`. |
| TLS material / SASL EXTERNAL | **Aligned** | Lean `selectSasl` prefers `EXTERNAL` when a client PEM pair or PKCS#12 bag is set; CI `lean-mtls` (plugin + CN mapping). Oracle TLS SM vector `sm_trace_tls.txt`. |

Residuals (documented, not silent): HMAC/SHA256 **hardness**; RS256/ES256; RabbitMQ regex engine / HA; park **exactly-once** server execution.

## Modules

| Lean | Python / SpeC++ |
|---|---|
| `NuropbRmq.Protocol.ConnState` | `nuropb_rmq.protocol.connection_sm.ConnState` |
| `NuropbRmq.Protocol.ChanState` | `nuropb_rmq.protocol.channel_sm.ChanState` |
| `NuropbRmq.Protocol.ConnectionSM` | `ConnectionStateMachine` + `ChannelStateMachine` |
| `NuropbRmq.Protocol.FrameDecode` | `nuropb_rmq.transport.frame` decode/encode bounds (`payload+8 ≤ frame_max`) |
| `NuropbRmq.Protocol.Bytes` / `Frame` / `Field` / `Methods` | Executable AMQP codec (Lean client + `lake exe oracle`). Field decode includes array/`x-death` tags used on DLQ. |
| `NuropbRmq.Pattern.Envelope` | JSON-RPC 2.0 body (`separators=(",", ":")`) |
| `NuropbRmq.Protocol.PublisherConfirms` | `transport/confirm.py` ConfirmTracker; SpeC++ `publisher_confirms*.smt2` |
| `NuropbRmq.Protocol.BasicReturn` | `basic.return` / mandatory publish; SpeC++ `basic_return*.smt2`; `PublishReturned` |
| `NuropbRmq.Protocol.DeliverySettle` | `basic_ack` / `basic_nack` / `basic_reject`; `NackDelivery` |
| `NuropbRmq.Protocol.Invariants` | SpeC++ invariants 1–7; PBTs under `tests/protocol/` + `tests/transport/` |
| `specs/specpp/Protocol/frame_bounds.smt2` | Wire-size ≤ frame_max |
| `specs/specpp/Protocol/connection_blocked.smt2` | Blocked must be handled (not silent drop) |
| `specs/specpp/Protocol/basic_return.smt2` | Return ≠ confirm nack; mandatory unroutable is observable |
| `specs/specpp/Protocol/connection_channel_sm.smt2` | Same sort universe as Lean `ConnState` / `ChanState` / `TlsState` |
| `NuropbRmq.Session.Correlation` | `nuropb_rmq.session.{ids,correlation,session}` |
| `NuropbRmq.Session.Invariants` | SpeC++ Session Phase 1b; PBTs under `tests/session/` |
| `NuropbRmq.Session.DeadLetterTimeout` | Broker TTL/DLX + `patterns/dlq_timeout.py` |
| `NuropbRmq.Session.Reconnect` | `session/reconnect.py` + `Session.reconnect` |
| `NuropbRmq.Session.Phase2Invariants` | SpeC++ Phase 2; PBTs under `tests/session/test_reconnect.py` |
| `NuropbRmq.Pattern.Mesh` | `nuropb_rmq.patterns.mesh` |
| `NuropbRmq.Pattern.Claims` | `nuropb_rmq.patterns.context` (`tryAuth` tree) |
| `NuropbRmq.Pattern.Jwt` | HS256 compact verify; PyJWT golden `tests/patterns/test_jwt_golden.py` |
| `NuropbRmq.Pattern.Acl` | `nuropb_rmq.patterns.acl`; `tests/patterns/test_acl.py`; `test_reply_acl_amqp.py` |
| `NuropbRmq.Crypto.Sha256` / `Hmac` | FIPS / RFC 4231 vectors in Lean `native_decide` |
| `NuropbRmq.Pattern.Invariants` | SpeC++ Pattern; PBTs under `tests/patterns/` |
| `NuropbRmq.Config.QueueProfile` | `nuropb_rmq.config.queue_profile` |
| `NuropbRmq.Config.Invariants` | SpeC++ Config; `tests/config/test_queue_profile.py` |
| `specs/specpp/Session/correlation.smt2` | Session correlation sorts / clauses |
| `specs/specpp/Session/phase2_reconnect.smt2` | Phase 2 terminal-state / reconnect epoch clauses |
| `specs/specpp/Pattern/mesh_claims.smt2` | Pattern mesh/claims sorts / clauses |
| `specs/specpp/Config/queue_profile.smt2` | Python `config/queue_profile.py` + Lean `NuropbRmq.Config` |

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
| `AuthOk` (`jti`/`method` bind + `authorizeOk`) | `jti`↔corr, `method` claim, then `authorize_func` |
| `specs/specpp/Pattern/mesh_claims.smt2` | PBTs under `tests/patterns/test_mesh.py` + `test_context.py` |

| Lean theorem(s) | Python / tests |
|---|---|
| `tryBind_ok_of_inNamespace`, `tryBind_refused_*`, `tryBind_exact_service` | `test_namespace_refuse`, `test_pbt_routing_key_in_namespace`, `test_pbt_exact_service_key` |
| `tryAuth_public_skip` | `test_public_method_skips_claims`, `test_pbt_public_skip` |
| `tryAuth_reject_*`, `tryAuth_ok` | `test_missing_claims_*`, `test_pbt_jti_must_match`, `test_authorize_func_denied` |

JWT HS256 compact verify is executable in `Pattern.Jwt` (not a PRF proof).
Broker ACL profiles are executable in `Pattern.Acl` (not the broker binary).
Live `test_reply_acl_amqp.py` and `scripts/smoke_lean_reply_acl.sh` use RabbitMQ
`write` on `amq.default` (default-exchange RPC) and wait for `channel.close` 403
— not a routing-key match.
Python also refuses empty method / `..` segments beyond the SpeC++ prefix core.

## Session Phase 2 (Reconnect + DeadLetterTimeout)

| Lean / SpeC++ | Python |
|---|---|
| `exclusiveFate` / TTL vs ack | Broker TTL/DLX authoritative; DLQ timeout synthesizer |
| DLQ unroutable `reply_to` | `DlqTimeoutProcessor` publishes `mandatory=true`; `basic.return` counted, drop unchanged |
| `terminalOf` acked / dlqTimeout / connectionLost | RPC result, DLQ `REQUEST_TIMEOUT`, `CONNECTION_LOST` |
| `onDisconnect` fail-fast clears pending | `Session` `fail_outstanding=True` |
| `onDisconnectPark` keeps pending | default park; `remember_publish` / republish |
| `onReconnect` bumps epoch, keeps parked count | `Session.reconnect` / `ReconnectCoordinator` |
| `MeshService.rebind` | Fresh connection + namespaced binds; caller restarts `RpcServer` |
| `specs/specpp/Session/phase2_reconnect.smt2` | `tests/session/test_reconnect.py` + integration |

## Config (SpeC++ + Lean)

| SpeC++ / Lean | Python |
|---|---|
| `Config/queue_profile.smt2` (sat) | `QueueProfile` durable ⇒ `delivery_mode=2` |
| `Config/queue_profile_negatives.smt2` (unsat) | publish refuse non-persistent on durable |
| `NuropbRmq.Config.consistent` / `durable_requires_persistent` | `QueueProfile.__post_init__` / `assert_delivery_mode` |
| `durableAtLeastOnce_consistent` | `DURABLE_AT_LEAST_ONCE` / `tests/config/test_queue_profile.py` |

## Runtime (dual clients)

Python and Lean are **two runtimes** over the same kernels. There is no
extraction in either direction. The Python 1.0 API (`src/nuropb_rmq/api.py`)
is frozen; Lean names mirror it and are not a Python API change.

| Role | Artifact |
|---|---|
| Proofs + kernels | Lake target `NuropbRMQSpec` (`import NuropbRmq.*`, no `IO`) |
| Lean AMQP/mesh client | Lake package / `import NuropbRMQ` (POSIX sockets; imports kernels) |
| Optional AMQPS | `NuropbRMQTls.connect` (OpenSSL tls-verify-full PEM or PKCS#12 + mTLS `EXTERNAL`; not `default_target`). |
| Python 1.0 | `nuropb_rmq` / PyPI `nuropb-rmq` (asyncio; no Lean FFI in the wheel) |

| Lean client | Python 1.0 |
|---|---|
| `NuropbRMQ.connect` / `connectWith` / `Transport` | `AmqpConnection` (PLAIN; TLS is a separate byte pipe) |
| `NuropbRMQ.Tls.connect` | `AmqpConnection` AMQPS `tls-verify-full` (PEM CA + optional client PEM or PKCS#12 / `EXTERNAL`) |
| `NuropbRMQ.Session` | `Session` |
| `NuropbRMQ.RpcClient` / `RpcServer` | `RpcClient` / `RpcServer` |
| `NuropbRMQ.MeshService` / `ServiceIdentity` | `MeshService` / `ServiceIdentity` |
| `NuropbRMQ.EventPublisher` / `EventSubscriber` | `EventPublisher` / `EventSubscriber` |
| `NuropbRMQ.MeshRegistryPublisher` / `MeshRegistryViewer` | `MeshRegistryPublisher` / `MeshRegistryViewer` |
| `NuropbRMQ.DlqTimeoutProcessor` | `DlqTimeoutProcessor` |
| `NuropbRmq.Protocol.tryStep` / `legalSend` | Python connection/channel SMs |
| `NuropbRmq.Pattern.Mesh.tryBind` | `MeshService.assert_bind_allowed` |
| `NuropbRmq.Pattern.Jwt.verifyHs256` | `AuthConfig.verify_request` (HS256) |

Interop suites (shared `nr.interop.*` keys so they do not clash with
`one_client_one_service`): `examples/interop_hello/`, `examples/interop_mesh/`,
`examples/lean_mesh/`. Smoke: `./scripts/smoke_interop.sh`.

## Build / test

```bash
python specs/specpp/check_sat.py
# from repository root
lake build NuropbRMQSpec
lake build NuropbRMQ
lake exe oracle .
pytest -q tests/protocol tests/transport tests/session tests/patterns
# claims unit tests need: uv sync --dev --extra claims
# integration (needs local RabbitMQ):
pytest -q tests/integration
# Lean ↔ Python interop (needs lake + broker):
./scripts/smoke_interop.sh
# Lean AMQPS (OpenSSL; not default lake build):
./scripts/smoke_lean_amqps.sh
# Lean IO coverage (claims / events / DLQ / reconnect; PLAIN):
./scripts/smoke_lean_coverage.sh
```
