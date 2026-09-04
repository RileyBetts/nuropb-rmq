# Roadmap

Dated **2026-09-04**. Python 1.0 (`src/nuropb_rmq/api.py`) stays frozen. This
is not a release schedule and does not claim Reservoir tags or a new PyPI
version.

## Done on `development`

- Optional process-local RPC request-id dedup (`dedup_window` / Lean
  `tryDedup`): handler at most once; park delivery stays at-least-once
- Lean RS256/ES256 verify on `NuropbRMQTls` (OpenSSL FFI + PyJWT goldens);
  Python `AuthConfig` verifies the same algs via PyJWT (`[claims]`)
- Python 1.0 review (2026-09-04): freeze held; kernels aligned; IO splits
  and `AmqpConnection.close` waiter residuals documented in CORRESPONDENCE
- Lean `authorize_func`: opaque `authorizeOk` on `tryAuth`, optional RPC hook
  after HS256 (deny/allow in Lean claims smoke)
- Scoped Lean/Python `matchesRegex` for documented ACL profiles plus a live
  narrower-than-prefix regex 403 (not RabbitMQ's full engine / HA)
- Dual runtime: Lean `Std.Async.TCP` (libuv) client (`import NuropbRMQ`) shares
  SpeC++ / Lean kernels with Python; no extraction either way
- Lean async IO (lean-grpc v1.3.0 shape): `AsyncByteTransport`, connection
  waiters, reply waiters (no `IO.sleep 20`), `requestAsync` overlap; public
  APIs are `Async` (`.block` only at process `main`)
- Lean AMQP IO: `TCP_NODELAY`, coalesced `encodeBurst` / one `aio.send`,
  64 KiB offset recv, `HashMap` confirm/reply waiters, session RPC cache,
  confirm overlapped with reply wait, server reply+ack one write,
  write-combine flush (`writePending` / one `aio.send`)
- PLAIN mesh + optional AMQPS (`NuropbRMQTls.connectAsync`, tls-verify-full
  PEM; UV-loop memory BIO / `SSL_ERROR_WANT_*`)
- mTLS PEM + PKCS#12 + SASL `EXTERNAL` (`NuropbRMQTls.connectAsync` +
  `selectSasl`; still not default `lake build`)
- Smokes: `scripts/smoke_interop.sh`, `smoke_lean_amqps.sh`,
  `smoke_lean_coverage.sh`, `smoke_lean_mtls.sh`, `smoke_lean_reply_acl.sh`,
  `smoke_lean_jwt_asymmetric.sh`, `smoke_lean_reply_acl_regex.sh`,
  `smoke_lean_rpc_overlap.sh`, `lake exe lean_async_tcp_smoke`
  (claims, events, DLQ, park/fail-fast reconnect, `lean_dedup_hello`,
  live `amq.default` 403, narrower regex 403, mTLS EXTERNAL, async waiters)
- CI: `lean` (includes `lean_async_tcp_smoke`), `lean-interop` (includes
  reply-forge 403 + regex 403 + RPC overlap), `lean-amqps`, `lean-mtls`
  (not required for merge except `Lean NuropbRMQSpec + NuropbRMQ`)

## Next (Lean IO)

_(empty — Lean IO residuals below)_

## Not claimed

- HMAC/SHA-256 hardness
- Full RabbitMQ regex engine / HA (scoped `matchesRegex` + live 403 are done)
- Park exactly-once *delivery* / clustered dedup (optional in-process
  `dedup_window` is handler-once only)
- LangChain / LangGraph in Lean (examples stay Python-only)
- Default `lake build` without OpenSSL (Lean mTLS / PKCS#12 stay on
  `NuropbRMQTls`)
- Porting Lean write-combine / dial hook / `requestAll` into frozen Python 1.0
- Lean `MeshService.announce` registry publish (Python already announces)

See [CHANGELOG Unreleased](../CHANGELOG.md), [testing regime](reference/testing-regime.md),
and [CORRESPONDENCE](../specs/lean/CORRESPONDENCE.md).
