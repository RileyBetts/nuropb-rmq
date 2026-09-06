# Roadmap

Dated **2026-09-05**. Python 1.0 (`src/nuropb_rmq/api.py`) stays frozen. This
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

## Next (best msgs/s)

Goal: the highest measured rate on **either** runtime. Python 1.0
`api.py` stays frozen. AMQP/mesh behavior stays 100% (confirms, one ack
per delivery, `basic.return`, blocked publish, quorum+DLX+TTL vs
`durable_classic()`).

- Done: firehose coalesce (`writeBatch` / `waitWritesIdle`). Docker
  PLAIN `:5672` raw 64 B Lean **~4.7k** vs Python **~3.1k** (42–43
  `uv_write`s / 2000). Loopback Python ~9.3k was not re-tested
  (Homebrew error).
- Done: Lean is first-class on lossy `event_fanout` (1 and 3 exclusive
  subscribers). Docker `:5672`: Lean **4406 / 4685** (1 sub) vs Python
  **2213 / 2771**. That cell is **not** trading at-least-once.
- This slice: durable fan-out is opt-in (named durable queue per
  consumer + confirm). RPC/mesh stays off the FIX critical path.
  Many-to-many event remasure (`P` pubs × `M` subs) is the capacity
  shape; serial RPC on one `Session` is an RTT probe only. See
  [events durability](concepts/events-durability.md).
- Pika exclusive RPC vs nuropb is a **no-confirm ceiling** plus a
  thinner stub, including on the fair asyncio peer (**140** vs **51**,
  p50 6.7 vs 15.4 ms). Blocking **162** vs **101** is a different IO
  model. Do not drop confirms. Product overlap is already Lean-led
  (~1.0k vs ~0.5–0.6k).
- A healthy Homebrew remasure is still the check against the ~9.3k
  loopback ceiling. Further hops are Std.Async
  ([lean4#13469](https://github.com/leanprover/lean4/issues/13469)), not
  another `pumpDrain` or event ack rewrite.
- Product RPC/mesh stays broker-RTT one-at-a-time. Quorum serial ≈ mesh
  classic serial; `durable_classic()` is the fast mesh profile.
- Still rejected: POSIX steal-the-socket, silent `multiple` ack, dropping
  confirms or the DLX.

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
