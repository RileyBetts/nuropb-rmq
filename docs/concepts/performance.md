# Performance

nuropb-rmq is an asyncio-native AMQP 0-9-1 client. Runtime code does not
depend on pika. A comparison harness under [`bench/`](../../bench/) runs
**pika `AsyncioConnection`** (same event loop) when you install the
optional `[bench]` extra. `BlockingConnection` + threads is a different
IO model (`--pika-io blocking`), not the fair peer.

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

Every remasure and `bench.compare` cell clocks **first measured send → last
complete** (ack, last fan-out copy, or RPC reply). Queue declare, bind,
`basic.consume`, `confirm.select`, session start, and one warmup
round-trip are **outside** the wall. Do not treat setup as throughput.

Recorded **blocking** pika run (2026-09-01): Docker RabbitMQ 3.13.7, PLAIN
on `127.0.0.1:5672` (no TLS), Python 3.12.12, pika 1.4.4, Intel Core
i7-8850H, macOS 15. That run is **not** apples-to-apples. Fair cells
(2026-09-05, same laptop, Docker `:5672`, pika 1.4.4
`AsyncioConnection`, 2000 msgs, conc 1) are in **How to read** below.
The harness writes JSON under [`bench/results/`](../../bench/results/).

## How to read the numbers

**Firehose (raw + fanout).** The fair peer is asyncio pika, not
`BlockingConnection`. Docker PLAIN `:5672`, 2000 msgs, conc 1,
2026-09-06 (`bench/results/20260906T114609Z.json`), clock is first
measured send → last complete:

| Workload | nuropb-rmq | pika asyncio |
|----------|------------|--------------|
| Raw 64 B | **2725** | 1720 |
| Raw 1 KiB | **3637** | 2020 |
| Fanout 64 B, 1 sub | **2731** | 2102 |
| Fanout 64 B, 3 sub | **1589** | 1265 |

The older **2×–3×** line compared nuropb to **blocking** pika and is
not a client win.

Raw “p50 latency” in the JSON is **queueing delay in a burst**, not
single-message RTT. Prefer messages/second for that scenario.

**Request/reply is off the FIX critical path.** One `Session` doing
hundreds of serial requests is an **RTT probe**, not a capacity number.
Real RPC load is many independent clients, each with a modest in-flight
window, and (if scaled) competing backends — `rpc_m2m` in
`remeasure_io`. Asyncio pika’s exclusive stub is still faster on the
serial cell (64 B: **140**/s vs **51**/s) because it has **no publisher
confirms**. Do not drop confirms to match it.

**Events (trading shape).** Defaults are a **lossy live bus**. Durable
fan-out (confirm + named queue per consumer) is a different cell — do
not mix rates. Many-to-many capacity is `P` publisher connections × `M`
subscriber connections (`--events-m2m`), not 1 pub × 1–3 exclusive
subs. See [events durability](events-durability.md).

## What this does not claim

- TLS, clustering, quorum queues, or a long-warmed broker
- A 2×–3× firehose win vs pika — that figure was `BlockingConnection`
- A production SLO — rerun `python -m bench.compare` where you deploy
  (default `--pika-io asyncio`)
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
(same shape as `bench/runners/nuropb_rpc.py`) — **not** mesh.
`MeshService.start` declares a **quorum** queue bound to `nr.mesh` plus a DLX.
See **Fair remasure: raw vs mesh** below.

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

### PLAIN firehose (historical)

Lean firehose here used **one** connection (pub+consume on the same pump).
RPC is exclusive-queue on the default exchange — **not** mesh.

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

## Fair remasure: raw vs mesh (2026-09-05)

Same laptop, Homebrew RabbitMQ 4.3.4. PLAIN `:5673`, AMQPS `:5674` (mTLS +
EXTERNAL). Lean raw firehose is now **dual-connection** (pub ∥ consume), matching
Python. RPC is three topologies so hop vs quorum is visible. Not an SLO.

| Topology | Shape |
|----------|--------|
| `raw_firehose` | Exclusive queue; no per-message confirm |
| `raw_serial` | AMQPS: publish+confirm+consume+ack (two RTTs) |
| `rpc_classic` | Exclusive auto-delete on the default exchange |
| `rpc_mesh_classic` | `nr.mesh` + `durable_classic()` work queue |
| `rpc_mesh_quorum` | `MeshService.start` default (quorum + DLX + TTL) |

Overlap: Python 8 sessions; Lean `requestAll` windows of 32.

Re-measured the same day after Lean `pumpDrain` (decode every complete frame
before the next `recv`) and Python `RpcClient.request` confirm∥reply
(`_publish_kick`, no `api.py` change). Raw rows below are a later remasure
the same day after Lean `flushWrites` matches asyncio `drain()` (background
flusher; await `uv_write` only above 64 KiB). RPC/mesh rows are unchanged.
Not an SLO.

### PLAIN (fair dual-connection)

| Workload | Pass | Python | Lean |
|----------|------|--------|------|
| Raw 64 B | 1 / 2 | **9038** / **9609** | 5878 / 5466 |
| Raw 1 KiB | 1 / 2 | **8119** / **8395** | 5398 / 5285 |
| Raw 16 KiB | 1 / 2 | **6203** / **6566** | 4018 / 4112 |
| `rpc_classic` serial | 1 / 2 | 765 / 754 | **776** / **761** |
| `rpc_classic` overlap | 1 / 2 | 1733 / **1611** | **1754** / 1580 |
| `rpc_mesh_classic` serial | 1 / 2 | **582** / **533** | 511 / 322 |
| `rpc_mesh_classic` overlap | 1 / 2 | 1361 / 1574 | **1604** / **1686** |
| `rpc_mesh_quorum` serial | 1 / 2 | 435 / 434 | **439** / **450** |
| `rpc_mesh_quorum` overlap | 1 / 2 | 1276 / 1403 | **1455** / **1482** |

### AMQPS

Raw and mesh-AMQPS rows are the earlier fair remasure (unchanged path).
`rpc_classic` re-measured after Python confirm∥reply.

| Workload | Pass | Python | Lean |
|----------|------|--------|------|
| Raw 64 B serial | 1 / 2 | **1502** / 1249 | 1461 / **1483** |
| Raw 1 KiB serial | 1 / 2 | 1315 / 1090 | **1497** / **1482** |
| Raw 16 KiB serial | 1 / 2 | **1364** / **1068** | 1032 / 1022 |
| `rpc_classic` serial | 1 / 2 | 483 / 497 | **611** / **604** |
| `rpc_classic` overlap | 1 / 2 | 963 / 1069 | **1328** / **1318** |
| `rpc_mesh_classic` serial | 1 / 2 | 433 / 318 | **474** / **438** |
| `rpc_mesh_classic` overlap | 1 / 2 | 1022 / 820 | **1337** / **1359** |
| `rpc_mesh_quorum` serial | 1 / 2 | 319 / 288 | **323** / **373** |
| `rpc_mesh_quorum` overlap | 1 / 2 | 887 / 610 | **1209** / **1226** |

Lean `pumpDrain` did **not** move firehose. Awaiting every `uv_write` did:
PLAIN raw 64 B went from ~3.2k to ~5.7k msgs/s. Parking until `writeBatch`
(8 KiB) or an urgent waiter cut `uv_write`s from ~2000 to **~43** per
2000 × 64 B. Docker PLAIN `:5672` (Homebrew error that evening): Lean
**4716 / 4709** vs Python **3176 / 3115** (timers on). The Homebrew
~9.3k Python row above is a different path and was not re-tested. PLAIN
session RPC stays in band with Python on the same run. `rpc_mesh_classic`
serial is noisy (511 / 322); overlap on the same hop is ~1.6k.
`rpc_mesh_quorum` serial sits next to mesh classic serial — broker-bound.

### Lean firehose slices (`NUROPB_BENCH_IO=1`)

Flagged counters on `lean_bench_live` (same Homebrew PLAIN dual-conn cell,
same day). Exclusive assemble (header decode + body copy only) and
`recv?` count show the leftover is not another decode pass.

| Slice (64 B, mean of two passes) | per msg |
|----------------------------------|---------|
| `aio.send` wait (`uv_write` complete) | **~143 µs** |
| `basicAck` (encode + enqueue) | ~36 µs |
| `tryReadFrame` / `offerDeliver` | ~16–17 µs each |
| `recv?` | ~13 µs (8 calls / 2000 msgs) |
| `encodePublish` / send enqueue | ~7–10 µs |
| assemble (exclusive) | **~0.4 µs** |

After park-until-`writeBatch` (2026-09-05 evening, Docker PLAIN `:5672`,
`NUROPB_BENCH_IO=1`):

| Slice (64 B) | Pass 1 / 2 |
|--------------|------------|
| `uv_writes` / 2000 msgs | **43** / **42** (was ~235, then ~2000) |
| `aio.send` per msg | **7 µs** / **14 µs** (was ~143 µs) |
| assemble | ~0.5 µs / ~0.4 µs |
| Lean msgs/s | **4716** / **4709** |
| Python msgs/s (same run) | 3176 / 3115 |

In-repo coalesce is done. On this Docker path Lean leads. A healthy
Homebrew remasure is the check against the ~9.3k loopback ceiling.
Do not spend another slice on assemble or `pumpDrain`.

### Event fanout (Lean first-class, 2026-09-05)

Same Docker PLAIN `:5672` path. One auto-delete **fanout** exchange;
exclusive auto-delete queues; per-delivery ack. 2000 × 64 B
`encodeNotification` / `publish`. Rate is **publishes**; wall waits
until every subscriber has every message (`count * subs` receives).
Publisher calls `waitWritesIdle` after the publish loop (same tail as
firehose). Wall excludes declare / bind / confirm.select and one warmup
publish. Not `bench.compare` / pika — Lean vs Python nuropb only.
Not an SLO.

| Workload | Pass | Python | Lean |
|----------|------|--------|------|
| `event_fanout` 1 sub | 1 / 2 | 2213 / 2771 | **4406** / **4685** |
| `event_fanout` 3 sub | 1 / 2 | 1454 / 1226 | **2490** / **2702** |

Lean leads both **lossy 1-pub** cells. The 3-sub drop is wait-for-N.
That is **not** trading at-least-once (exclusive auto-delete queues).
Capacity shape is `--events-m2m` (`P` pubs × `M` subs, lossy and
durable columns). Serial RPC remains an RTT probe only.

Pika exclusive RPC on 2026-09-06, **asyncio** peer
(`bench.compare --pika-io asyncio`, 2000 msgs, conc 1, 64 B) was **123**
vs nuropb **83** (p50 7.4 vs 10.9 ms). Direct-reply ceiling **153**.
Both pika cells are a **no-confirm** stub, not a write-path hunt.
Product overlap stays Lean-led (`rpc_classic` overlap in the table
below).

## Full remasure 2026-09-06 (post clock fix)

Same i7-8850H laptop. Docker `rmq-plain` on `127.0.0.1:5672` and
`rmq-amqps-mtls` on `127.0.0.1:5671`. Two passes. Wall is **first
measured send → last complete**; declare / bind / consume /
`confirm.select` / session start / one warmup are outside the clock.
Log: [`bench/results/remeasure_20260906T1139Z.log`](../../bench/results/remeasure_20260906T1139Z.log).
Not an SLO. Homebrew `:5673` / `:5674` was **not** re-run (service in
error). Lean has no `rpc_m2m` cell.

### PLAIN Docker (`:5672`, raw = firehose)

| Workload | Pass | Python | Lean |
|----------|------|--------|------|
| Raw 64 B | 1 / 2 | 2984 / 2675 | **4954** / **5249** |
| Raw 1 KiB | 1 / 2 | 2982 / 3860 | **4823** / **4806** |
| Raw 16 KiB | 1 / 2 | 959 / 779 | **1098** / **1168** |
| `rpc_classic` serial | 1 / 2 | 130 / 131 | **157** / **164** |
| `rpc_classic` overlap | 1 / 2 | 563 / 571 | **1103** / **965** |
| `rpc_mesh_classic` serial | 1 / 2 | 77 / 130 | **124** / **133** |
| `rpc_mesh_classic` overlap | 1 / 2 | 180 / 407 | **1064** / **881** |
| `rpc_mesh_quorum` serial | 1 / 2 | 95 / 81 | **111** / **95** |
| `rpc_mesh_quorum` overlap | 1 / 2 | 448 / 339 | **905** / **721** |
| `event_fanout` 1 sub | 1 / 2 | 3295 / 3053 | **5125** / **4559** |
| `event_fanout` 3 sub | 1 / 2 | 2007 / 1582 | **2700** / **2652** |
| `event_fanout_m2m` 4×4 lossy | 1 / 2 | 1496 / 1268 | **2134** / **2121** |
| `event_fanout_m2m` 4×4 durable | 1 / 2 | 212 / 274 | **326** / **319** |
| `rpc_m2m` 4 clients × 2 backends | 1 / 2 | 1031 / 895 | — |

Durable m2m is **confirm-bound** (~200–330 pubs/s). Do not mix with
lossy m2m. Serial RPC is an RTT probe. `rpc_m2m` is the non-critical
RPC capacity shape.

### AMQPS Docker (`:5671`, raw = serial confirm+ack)

| Workload | Pass | Python | Lean |
|----------|------|--------|------|
| Raw 64 B serial | 1 / 2 | 288 / 290 | **309** / **303** |
| Raw 1 KiB serial | 1 / 2 | 293 / **297** | **321** / 293 |
| Raw 16 KiB serial | 1 / 2 | 231 / **247** | 236 / 237 |
| `rpc_classic` serial | 1 / 2 | 139 / 131 | **164** / **138** |
| `rpc_classic` overlap | 1 / 2 | 436 / 455 | **921** / **983** |
| `rpc_mesh_classic` serial | 1 / 2 | **111** / 107 | 72 / **135** |
| `rpc_mesh_classic` overlap | 1 / 2 | 386 / 376 | **448** / **919** |
| `rpc_mesh_quorum` serial | 1 / 2 | **88** / 84 | 57 / **90** |
| `rpc_mesh_quorum` overlap | 1 / 2 | 325 / 290 | **336** / **646** |
| `event_fanout` 1 sub | 1 / 2 | 1477 / 2074 | **4618** / **3752** |
| `event_fanout` 3 sub | 1 / 2 | 834 / 1159 | **2158** / **2184** |
| `event_fanout_m2m` 4×4 lossy | 1 / 2 | 866 / 1029 | **1858** / **2095** |
| `event_fanout_m2m` 4×4 durable | 1 / 2 | 252 / 233 | **259** / **245** |
| `rpc_m2m` 4×2 | 1 / 2 | 666 / 634 | — |

AMQPS raw is two broker RTTs per message. Event firehose still leads
on Lean. Durable m2m stays in the confirm band on both languages.

### Lean RPC / mesh slices (`NUROPB_BENCH_IO=1`)

Same Homebrew PLAIN path, same day, after `runRpc` gained the same counters
plus confirm-wait / reply-wait. Lean vs Lean. Serial wall is **broker RTT**,
not assemble.

| Slice (`rpc_mesh_classic` serial, mean of two passes) | per msg |
|-------------------------------------------------------|---------|
| confirm wait (`awaitExceptAsync` on publisher confirm) | **~3.8 ms** |
| reply wait (`waitReplyWaiterAsync`) | **~3.6 ms** |
| `aio.send` | ~0.58 ms |
| assemble (exclusive) | **~1.7 µs** |
| `recv?` calls | ~3 / msg (blocks until frames; same wait as reply) |

`rpc_classic` serial is the same shape with a cheaper confirm (~1.1 ms
confirm, ~2.7 ms reply). Overlap `reply_wait` looks large per request
because windows overlap; wall-clock overlap still lands ~1.0–1.4k with
timers on (uninstrumented ~1.6k). Quorum serial pass 1 in this instrumented
run dropped to 60 msgs/s with ~14 ms confirm wait — RTT / broker stall,
same class as the uninstrumented 322 mesh-classic pass.

Accept confirm + reply wait (correct AMQP). Do not drop confirms,
per-delivery ack, or quorum DLX+TTL. Do not spend client IO on
`rpc_mesh_quorum`. `MeshService.announce` stays unwired Lean drift
(behavior backlog, not a perf cell).

```bash
# Lean vs Python IO remasure (not an SLO).
# Local Homebrew defaults: PLAIN :5673, AMQPS :5674
./scripts/remeasure_lean_python.sh
./scripts/remeasure_lean_python.sh --plain --raw
./scripts/remeasure_lean_python.sh --plain --events --plain-port 5672
./scripts/remeasure_lean_python.sh --plain --events-m2m --rpc-m2m --plain-port 5672
./scripts/remeasure_lean_python.sh --plain --rpc --mesh
./scripts/remeasure_lean_python.sh --amqps --mesh
./scripts/remeasure_lean_python.sh --plain-port 5672 --amqps-port 5671

uv sync --dev --extra bench
# fair peer is pika AsyncioConnection (default):
uv run python -m bench.compare
uv run python -m bench.compare --quick
# different IO model, not the fair compare:
uv run python -m bench.compare --pika-io blocking --quick
```
