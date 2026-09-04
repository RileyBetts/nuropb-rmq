# Lean async IO model

NuropbRMQ uses Lean 4 `Std.Async.TCP` (libuv-backed) for PLAIN sockets, matching
the [lean-grpc `docs/async-io.md`](https://github.com/RileyBetts/lean-grpc/blob/main/docs/async-io.md)
v1.3.0 split. AMQP waiters stay the Python `_read_loop` shape: one reader,
serialized writes, and tables for method / confirm / deliver / reply.

AMQPS uses the same UV loop: `Std.Async.TCP` plus a memory-BIO OpenSSL session
(`SSL_ERROR_WANT_READ` / `WANT_WRITE`). There is no off-loop `SSL_*` and no
`SSL_set_fd`.

This is a **runtime** change. Kernels stay in `NuropbRMQSpec` (no UV scheduler
theorems). Python 1.0 `api.py` is unchanged.

## Layers

| Layer | Behavior |
|---|---|
| `AsyncByteTransport` / `tcpTransportAsync` | Native `Async` send/recv — **no** `.block` |
| `connectAsync` / `receiveAsync` / `requestAsync` / `serveAsync` | Library AMQP entry points (`Async`) |
| `NuropbRMQTls.connectAsync` | Same loop: TCP + memory BIO handshake + `connectWithAsync` |
| `Transport.ofAsync` | Loopback smoke adapter only |

```text
  App (Async) ──► requestAsync / serveAsync / connectAsync     (PLAIN)
              └─► NuropbRMQTls.connectAsync                   (TLS on UV)
                      │
                      ▼
              Std.Async.TCP ──► ciphertext
              OpenSSL memory BIO ──► SSL_do_handshake / SSL_read / SSL_write
              SSL mutex serializes pump recv and flushWrites

  App (IO) ──► runAsync / `.block` at process `main` only
```

## UV loop ownership

Prefer **one** event-loop owner per process. Nested `.block` inside
`IO.asTask` workers is unsupported (lean-grpc `TrailersLoopback` lesson).
Use `Std.Async.background` to schedule connections and overlapping RPCs
under Async.

`ConnState` waiter tables are updated with `modify`, not a stale
`get`/`set` snapshot: the pump must not wipe in-flight confirm or reply
waiters. Confirm and reply waiters are `Std.HashMap` (method waiters stay
lists). After PLAIN dial, `TCP.Socket.Client.noDelay` sets `TCP_NODELAY`.
`encodeBurst` concatenates method+header+body into one `ByteArray` and
`sendBurstAsync` issues one `aio.send`. Inbound recvs 64 KiB and advances a
buffer offset (compact when the dead prefix is large vs remaining size).
`lastPeerMs` is refreshed on heartbeat / idle, not every method frame.
`requestAsync` registers the confirm waiter and the reply waiter together
(`Async.concurrently`) so the two broker RTTs overlap. `serveOnceAsync`
writes the JSON-RPC reply and the request `basic.ack` in one `aio.send`
(Python `drain=False` on the reply, drain on the ack). Pumped writes enqueue
complete bursts on `writePending`; one flusher concatenates and issues a
single `aio.send` (no mid-frame splice).

## TLS (memory BIO on the UV loop)

`NuropbRMQTls` allocates an `SSL*` with a pair of memory BIOs. Ciphertext
moves through `Std.Async.TCP`; plaintext is `SSL_read` / `SSL_write`.
Handshake is `SSL_do_handshake` plus `WANT_READ` / `WANT_WRITE`. An async
mutex around the session keeps the pump and write flusher from entering
OpenSSL together (`SSL*` is not concurrent). A C `pthread` lock on the
same session is the backstop. OpenSSL is initialized with
`OPENSSL_INIT_NO_ATEXIT` so process `exit` does not `OPENSSL_cleanup`
while the UV thread is still resolving a `recv`. `Connection.close` fails
waiters before `SSL_free`. TCP `recv?` is serialized (libuv forbids
parallel recv on one client).

Default `lake build NuropbRMQ` links **libuv** via `Std.Async` and still does
**not** link OpenSSL. Do not reintroduce POSIX steal-the-socket.

`Session.startAsync` takes a `dial` hook. PLAIN is the default. AMQPS
passes `NuropbRMQTls.defaultDial` so the default client does not import
OpenSSL.

## Tests

| Smoke | Broker | What it gates |
|---|---|---|
| `lake exe lean_async_tcp_smoke` | no | Refused dial, loopback `Async` send/recv, `.block` adapter, waiter completion |
| `./scripts/smoke_lean_rpc_overlap.sh` | yes | One session, eight in-flight stub RPCs |
| `./scripts/smoke_lean_amqps.sh` | AMQPS | UV-loop TLS connect |
| `./scripts/smoke_lean_mtls.sh` | AMQPS mTLS | PEM / PKCS#12 + `EXTERNAL` |
| existing IO smokes | yes | Examples call `runAsync` once in `main` |

## What this does not claim

- HMAC/SHA-256 hardness
- A second libc `poll` loop beside `Std.Async.TCP`
- Formal proofs of the UV scheduler
- A throughput SLO (overlap is a correctness/perf smoke, not a capacity number)
