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

    consumer_task = asyncio.create_task(consume_loop())

    publishers: list[AmqpConnection] = []
    per = message_count // concurrency
    rem = message_count % concurrency

    async def publish_worker(n: int) -> None:
        conn = AmqpConnection(cfg)
        publishers.append(conn)
        await conn.connect()
        ch = await conn.open_channel(1)
        loop = asyncio.get_running_loop()
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
            asyncio.create_task(publish_worker(per + (1 if i < rem else 0)))
            for i in range(concurrency)
        ]
        await asyncio.gather(*tasks)
        await asyncio.wait_for(done.wait(), timeout=max(30.0, message_count * 0.01))
    await consumer_task

    for p in publishers:
        await p.close()
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
