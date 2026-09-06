# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""nuropb-rmq: raw publish → consume → ack."""

from __future__ import annotations

import asyncio
import uuid

from bench.common import (
    BenchResult,
    Stopwatch,
    broker_host,
    broker_port,
    make_payload,
    summarize_latencies_ms,
    timed_msgs_per_sec,
)
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig


async def run_raw_publish_consume(
    *,
    payload_bytes: int,
    concurrency: int,
    message_count: int,
) -> BenchResult:
    cfg = ConnectionConfig(host=broker_host(), port=broker_port())
    queue = f"nr.bench.raw.{uuid.uuid4().hex}"
    body = make_payload(payload_bytes)
    latencies: list[float] = []
    lat_lock = asyncio.Lock()

    consumer = AmqpConnection(cfg)
    await consumer.connect()
    ch_c = await consumer.open_channel(1)
    await consumer.queue_declare(ch_c, queue, auto_delete=True)
    await consumer.basic_consume(ch_c, queue)

    done = asyncio.Event()
    received = 0

    async def consume_loop() -> None:
        nonlocal received
        while received < message_count:
            msg = await consumer.receive(timeout=None)
            headers = msg.properties.get("headers") or {}
            t0_us = headers.get("t0_us")
            if isinstance(t0_us, int):
                async with lat_lock:
                    latencies.append(asyncio.get_running_loop().time() - (t0_us / 1_000_000))
            await consumer.basic_ack(ch_c, msg.delivery_tag)
            received += 1
        done.set()

    publishers: list[tuple[AmqpConnection, int]] = []
    per = message_count // concurrency
    rem = message_count % concurrency
    for _ in range(concurrency):
        conn = AmqpConnection(cfg)
        await conn.connect()
        ch = await conn.open_channel(1)
        publishers.append((conn, ch))

    loop = asyncio.get_running_loop()
    await publishers[0][0].basic_publish(
        publishers[0][1],
        body,
        routing_key=queue,
        properties={"content_type": "application/octet-stream"},
    )
    warm = await consumer.receive(timeout=None)
    await consumer.basic_ack(ch_c, warm.delivery_tag)

    consumer_task = asyncio.create_task(consume_loop())

    async def publish_worker(conn: AmqpConnection, ch: int, n: int) -> None:
        for _ in range(n):
            t0_us = int(loop.time() * 1_000_000)
            await conn.basic_publish(
                ch,
                body,
                routing_key=queue,
                properties={
                    "headers": {"t0_us": t0_us},
                    "content_type": "application/octet-stream",
                },
            )

    with Stopwatch() as sw:
        tasks = [
            asyncio.create_task(
                publish_worker(publishers[i][0], publishers[i][1], per + (1 if i < rem else 0))
            )
            for i in range(concurrency)
        ]
        await asyncio.gather(*tasks)
        await asyncio.wait_for(done.wait(), timeout=max(30.0, message_count * 0.01))
    await consumer_task

    for conn, _ch in publishers:
        await conn.close()
    await consumer.close()

    p50, p99 = summarize_latencies_ms(latencies)
    return BenchResult(
        library="nuropb-rmq",
        scenario="raw_publish_consume",
        payload_bytes=payload_bytes,
        concurrency=concurrency,
        message_count=message_count,
        wall_seconds=sw.elapsed,
        msgs_per_sec=timed_msgs_per_sec(message_count, sw.elapsed),
        latency_p50_ms=p50,
        latency_p99_ms=p99,
    )
