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

```bash
uv sync --dev --extra bench
# full default matrix (needs a broker on 5672 or 5673):
uv run python -m bench.compare
# smaller smoke:
uv run python -m bench.compare --quick
```
