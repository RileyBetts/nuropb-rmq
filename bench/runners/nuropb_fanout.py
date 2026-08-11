"""nuropb-rmq: fanout notification publish → N subscribers."""

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
from nuropb_rmq.patterns.events import EventPublisher, EventSubscriber
from nuropb_rmq.transport.connection import ConnectionConfig, IncomingMessage


async def run_event_fanout(
    *,
    payload_bytes: int,
    concurrency: int,
    message_count: int,
    subscribers: int = 1,
) -> BenchResult:
    cfg = ConnectionConfig(host=broker_host(), port=broker_port())
    exchange = f"nr.bench.fanout.{uuid.uuid4().hex}"
    payload = make_payload(payload_bytes).decode("latin-1")
    latencies: list[float] = []
    # Each message should be received by every subscriber
    target = message_count * subscribers
    counter = 0
    lock = asyncio.Lock()
    done = asyncio.Event()

    async def handler(method: str, params: object, msg: IncomingMessage) -> None:
        nonlocal counter
        headers = msg.properties.get("headers") or {}
        # notifications don't carry headers from EventPublisher today — latency optional
        _ = method, params, headers
        async with lock:
            counter += 1
            if counter >= target:
                done.set()

    subs = [
        EventSubscriber(cfg, exchange=exchange, exchange_type="fanout", handler=handler)
        for _ in range(subscribers)
    ]
    for s in subs:
        await s.start()

    pub = EventPublisher(cfg, exchange=exchange, exchange_type="fanout")
    await pub.start()

    per = message_count // concurrency
    rem = message_count % concurrency

    async def publish_worker(n: int) -> None:
        for _ in range(n):
            await pub.publish("", "bench.event", {"b": payload})

    try:
        with Stopwatch() as sw:
            await asyncio.gather(
                *[
                    publish_worker(per + (1 if i < rem else 0))
                    for i in range(concurrency)
                ]
            )
            await asyncio.wait_for(done.wait(), timeout=max(30.0, message_count * 0.02))
    finally:
        await pub.close()
        for s in subs:
            await s.close()

    p50, p99 = summarize_latencies_ms(latencies)
    return BenchResult(
        library="nuropb-rmq",
        scenario="event_fanout",
        payload_bytes=payload_bytes,
        concurrency=concurrency,
        message_count=message_count,
        wall_seconds=sw.elapsed,
        msgs_per_sec=timed_msgs_per_sec(message_count, sw.elapsed),
        latency_p50_ms=p50,
        latency_p99_ms=p99,
        notes=f"subscribers={subscribers}",
        extra={"subscribers": subscribers, "deliveries": target},
    )
