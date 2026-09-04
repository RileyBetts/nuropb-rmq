# Performance

nuropb-rmq is an asyncio-native AMQP 0-9-1 client. Runtime code does not
depend on pika. A comparison harness under [`bench/`](../../bench/) can still
run **pika** (`BlockingConnection` + threads) as a baseline when you install
the optional `[bench]` extra.

These figures are **one laptop run**, not a service-level objective. Re-run
on the hardware and broker you ship if you need capacity numbers.

## What the harness measures

Default matrix (`uv run python -m bench.compare`): 10,000 messages per cell;
payloads 64 / 1,024 / 16,384 bytes; 1 and 8 publishers; fanout with 1 and 3
subscribers.

| Workload | Meaning |
|----------|---------|
| Raw publish/consume | Body to a queue, consume and ack — codec and connection path |
| RPC exclusive reply | nuropb `Session` + JSON-RPC stub reply (the mesh-shaped path). Pika has a thinner exclusive-queue clone |
| Pika `amq.rabbitmq.reply-to` | Broker shortcut RPC; nuropb does not use it — a ceiling for “minimal AMQP RPC on this box” |
| Event fanout | One publish copied to N subscribers. Rate is **publishes**; the run waits until every subscriber has seen every message |

Recorded run (2026-09-01): Docker RabbitMQ 3.13.7, PLAIN on `127.0.0.1:5672`
(no TLS), Python 3.12.12, pika 1.4.4, Intel Core i7-8850H, macOS 15. The
harness writes JSON under [`bench/results/`](../../bench/results/).

## How to read the numbers

**Firehose (raw + fanout).** At 64-byte and 1 KiB bodies, nuropb-rmq moved
about **2×–3×** as many messages per second as blocking pika (for example
~5,800 vs ~2,000 msgs/s raw at 64 bytes, one publisher). At **16 KiB** both
clients sat in the same band (~1,500–1,650 msgs/s raw): broker copies and
Docker networking dominate, not the Python client. Extra publishers did not
help raw consume much — there is still one consumer.

Raw “p50 latency” in the JSON is **queueing delay in a 10,000-message burst**,
not single-message RTT. Prefer messages/second for that scenario.

**Request/reply.** Pika’s blocking exclusive-queue loop is faster. One client,
small request: on the order of **~145 round trips/s** for nuropb (median
~6–7 ms) vs **~250/s** for pika (median ~4 ms). Eight parallel clients:
roughly **~690/s** vs **~770/s**; pika `direct-reply-to` was a bit higher
still (~900/s). Plan mesh RPC as **hundreds of JSON-RPC round trips per
second per process** on similar hardware, not thousands.

That split is expected: cost sits on the session / exclusive reply queue /
JSON-RPC envelope, not on shoving bytes at a queue.

## What this does not claim

- TLS, clustering, quorum queues, or a long-warmed broker
- Fairness vs pika’s asyncio adapter (the harness uses `BlockingConnection`)
- A production SLO — rerun `python -m bench.compare` where you deploy
- Lean vs Python capacity numbers as a guarantee. See **Lean vs Python IO**
  below. Overlap smoke (`smoke_lean_rpc_overlap.sh`) is a correctness gate,
  not an SLO.

## Lean vs Python IO

Re-measured 2026-09-04 on the same i7-8850H laptop, Docker `rmq-plain`
(`rabbitmq:3-management`) on `127.0.0.1:5672` (TLS env unset). Lean PLAIN is
`Std.Async.TCP` (libuv) with one `aio.send` per publish burst, `TCP_NODELAY`,
a 64 KiB offset recv buffer, and `HashMap` confirm/reply waiters. RPC waits
for publisher confirm and the reply **together**. The stub server sends the
reply publish and request `basic.ack` in one write. Python is asyncio
`basic_publish` + one `_drain()`. Raw here is a **firehose** (publish without
per-message confirm wait; consume+ack in parallel). Cells: raw 2000 / 2000 /
1000; RPC 200 serial and 400 overlapping.

| Workload | Pass | Python | Lean |
|----------|------|--------|------|
| Raw 64 B | 1 / 2 | **4113** / **4077** | 4067 / 3691 |
| Raw 1 KiB | 1 / 2 | **4676** / **4561** | 3723 / 2740 |
| Raw 16 KiB | 1 / 2 | **1646** / **1718** | 1278 / 1244 |
| RPC serial 64 B | 1 / 2 | 133 / 133 | **250** / **218** |
| RPC overlap 64 B | 1 / 2 | 587 / 605 (8 sessions) | **1183** / **1135** (32 in-flight) |

Raw sits in the same few-k msgs/s band; Python led this pair. Lean RPC stayed
ahead. Lean overlap is `requestAll` in windows of 32 on one session (400 at
once can drop a UV promise). The morning Lean raw **~17310** was POSIX
steal-the-socket and is gone. **Not** a 17k claim and **not** an SLO.

These RPC cells use a **classic auto-delete** queue on the default exchange
(same shape as `bench/runners/nuropb_rpc.py`). `MeshService.start` declares a
**quorum** queue bound to `nr.mesh` plus a DLX. Mesh capacity is
broker/quorum-bound and will sit below this exclusive-reply table.

### Honesty

- Lean raw 64 B is in the same band as Python on this box, not a guaranteed
  win. SHA-256 / HMAC / HS256 stay residual (computable kernels vs hashlib).
- Mesh Lean code is not the RPC bottleneck; quorum + the extra exchange hop
  are. Do not treat these classic-queue numbers as a mesh SLO.
- AMQPS is the same UV loop as PLAIN (memory BIO / `SSL_ERROR_WANT_*`). See
  [`lean-async-io.md`](../reference/lean-async-io.md). Do not treat the AMQPS
  table as an SLO.

## Lean vs Python AMQPS

Same laptop, Docker `rmq-amqps-mtls` on `127.0.0.1:5671`, `tls-verify-full` +
client PEM (`NUROPB_RMQ_TLS=1`, CA + client cert, SNI `localhost`). Lean uses
`NuropbRMQTls.connectAsync` (UV-loop memory BIO; no `SSL_set_fd`). Re-measured
2026-09-04 on `rmq-amqps-mtls`.

**Raw** cells are **serial** publish + publisher-confirm + consume + ack on
one connection (two broker RTTs per message). That is slower than the PLAIN
firehose and is the fair Lean/Python pair on this path. Counts match the PLAIN
IO table: raw 2000 / 2000 / 1000; RPC 200 serial and 400 overlapping.

| Workload | Pass | Python | Lean |
|----------|------|--------|------|
| Raw 64 B | 1 / 2 | 459 / 429 | **471** / **447** |
| Raw 1 KiB | 1 / 2 | 421 / **456** | **481** / 417 |
| Raw 16 KiB | 1 / 2 | **366** / **377** | 363 / 346 |
| RPC serial 64 B | 1 / 2 | 128 / 126 | **224** / **215** |
| RPC overlap 64 B | 1 / 2 | 452 / 455 (8 sessions) | **1075** / **1055** (32 in-flight) |

No `SIGSEGV` (exit 139) at 1 KiB or 16 KiB. Serial raw sits in the same RTT
band. Lean RPC stays ahead. Python overlap is eight sessions; Lean overlap is
`requestAll` in windows of 32. Do not treat these as an AMQPS SLO.

## Homebrew RabbitMQ 4 (loopback)

Same laptop, same cells, Homebrew **RabbitMQ 4.3.4** on the host (not Docker).
PLAIN on `127.0.0.1:5673`. AMQPS on `127.0.0.1:5674` (`tls-verify-full` + client
PEM, SNI `localhost`, SASL EXTERNAL / `nuropb-client`) because Docker
`rmq-amqps-mtls` already owns host `:5671`. Re-measured 2026-09-04.

RabbitMQ 4 rejects transient **non-exclusive** queues, so these cells declare
**exclusive + auto-delete** (the Docker 3.13 tables used `auto_delete` only).
Loopback without Docker NAT is a different path; do not compare these rates
to the Docker tables as a client win.

### PLAIN firehose

| Workload | Pass | Python | Lean |
|----------|------|--------|------|
| Raw 64 B | 1 / 2 | **7782** / **8774** | 4936 / 4935 |
| Raw 1 KiB | 1 / 2 | **7726** / **8578** | 4317 / 4883 |
| Raw 16 KiB | 1 / 2 | **5362** / **5452** | 3972 / 3806 |
| RPC serial 64 B | 1 / 2 | **753** / **666** | 566 / 658 |
| RPC overlap 64 B | 1 / 2 | **1690** / **1514** (8 sessions) | 946 / 1105 (32 in-flight) |

### AMQPS serial raw

| Workload | Pass | Python | Lean |
|----------|------|--------|------|
| Raw 64 B | 1 / 2 | **1519** / **1548** | 1221 / 1517 |
| Raw 1 KiB | 1 / 2 | **1506** / 1433 | 1137 / **1551** |
| Raw 16 KiB | 1 / 2 | **1342** / **1321** | 962 / 1040 |
| RPC serial 64 B | 1 / 2 | **595** / 429 | 492 / **589** |
| RPC overlap 64 B | 1 / 2 | **1233** / 708 (8 sessions) | 1118 / **1340** (32 in-flight) |

On this host path Python led most raw cells. RPC is in the same band; pass-to-pass
spread is large (Python AMQPS overlap 1233 vs 708). Still **not** an SLO.

```bash
# Lean vs Python IO remasure (exclusive queues; not an SLO).
# Local Homebrew defaults: PLAIN :5673, AMQPS :5674
./scripts/remeasure_lean_python.sh
./scripts/remeasure_lean_python.sh --plain
./scripts/remeasure_lean_python.sh --amqps
./scripts/remeasure_lean_python.sh --plain-port 5672 --amqps-port 5671

uv sync --dev --extra bench
# full default matrix (needs a broker on 5672 or 5673):
uv run python -m bench.compare
# smaller smoke:
uv run python -m bench.compare --quick
```
