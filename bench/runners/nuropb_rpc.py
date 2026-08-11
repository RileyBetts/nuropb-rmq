"""nuropb-rmq: RPC over exclusive reply queue."""

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
from nuropb_rmq.patterns.rpc import RpcClient, RpcServer
from nuropb_rmq.session.session import Session
from nuropb_rmq.transport.connection import ConnectionConfig


async def run_rpc_exclusive(
    *,
    payload_bytes: int,
    concurrency: int,
    message_count: int,
) -> BenchResult:
    cfg = ConnectionConfig(host=broker_host(), port=broker_port())
    queue = f"nr.bench.rpc.{uuid.uuid4().hex}"
    payload = make_payload(payload_bytes).decode("latin-1")
    latencies: list[float] = []

    async def handler(method: str, params: object) -> object:
        return {"echo": params}

    server = RpcServer(cfg, queue=queue, handler=handler)
    await server.start()

    async def client_worker(n: int) -> None:
        session = Session(cfg)
        await session.start()
        client = RpcClient(session)
        loop = asyncio.get_running_loop()
        try:
            for _ in range(n):
                t0 = loop.time()
                await client.request(queue, "bench.echo", {"b": payload})
                latencies.append(loop.time() - t0)
        finally:
            await session.close()

    per = message_count // concurrency
    rem = message_count % concurrency
    try:
        with Stopwatch() as sw:
            await asyncio.gather(
                *[
                    client_worker(per + (1 if i < rem else 0))
                    for i in range(concurrency)
                ]
            )
    finally:
        await server.close()

    p50, p99 = summarize_latencies_ms(latencies)
    return BenchResult(
        library="nuropb-rmq",
        scenario="rpc_exclusive_reply",
        payload_bytes=payload_bytes,
        concurrency=concurrency,
        message_count=message_count,
        wall_seconds=sw.elapsed,
        msgs_per_sec=timed_msgs_per_sec(message_count, sw.elapsed),
        latency_p50_ms=p50,
        latency_p99_ms=p99,
    )
