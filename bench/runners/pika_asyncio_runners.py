# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""pika AsyncioConnection runners — same event-loop model as nuropb-rmq."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable

import pika
from pika.adapters.asyncio_connection import AsyncioConnection
from pika.exchange_type import ExchangeType

from bench.common import (
    BenchResult,
    Stopwatch,
    broker_host,
    broker_port,
    make_payload,
    summarize_latencies_ms,
    timed_msgs_per_sec,
)


def _params() -> pika.ConnectionParameters:
    return pika.ConnectionParameters(
        host=broker_host(),
        port=broker_port(),
        credentials=pika.PlainCredentials("guest", "guest"),
        heartbeat=60,
    )


class _AioConn:
    """Minimal awaitable wrapper around pika's callback AsyncioConnection."""

    def __init__(self) -> None:
        self.conn: AsyncioConnection | None = None
        self.ch: Any = None
        self._closed = asyncio.Event()

    async def connect(self) -> _AioConn:
        loop = asyncio.get_running_loop()
        opened: asyncio.Future[AsyncioConnection] = loop.create_future()

        def on_open(conn: AsyncioConnection) -> None:
            if not opened.done():
                opened.set_result(conn)

        def on_open_error(_conn: AsyncioConnection, exc: BaseException) -> None:
            if not opened.done():
                opened.set_exception(exc)

        def on_close(_conn: AsyncioConnection, _exc: BaseException) -> None:
            self._closed.set()

        self.conn = AsyncioConnection(
            _params(),
            on_open_callback=on_open,
            on_open_error_callback=on_open_error,
            on_close_callback=on_close,
            custom_ioloop=loop,
        )
        await opened
        ch_fut: asyncio.Future[Any] = loop.create_future()

        def on_ch(ch: Any) -> None:
            if not ch_fut.done():
                ch_fut.set_result(ch)

        self.conn.channel(on_open_callback=on_ch)
        self.ch = await ch_fut
        return self

    async def _ok(self, method: str, **kwargs: Any) -> Any:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()

        def cb(frame: Any) -> None:
            if not fut.done():
                fut.set_result(frame)

        kwargs["callback"] = cb
        getattr(self.ch, method)(**kwargs)
        return await fut

    async def queue_declare(self, queue: str, **kwargs: Any) -> Any:
        return await self._ok("queue_declare", queue=queue, **kwargs)

    async def exchange_declare(self, exchange: str, **kwargs: Any) -> Any:
        return await self._ok("exchange_declare", exchange=exchange, **kwargs)

    async def queue_bind(self, queue: str, exchange: str, routing_key: str = "") -> Any:
        return await self._ok("queue_bind", queue=queue, exchange=exchange, routing_key=routing_key)

    def publish(
        self,
        exchange: str,
        routing_key: str,
        body: bytes,
        properties: pika.BasicProperties | None = None,
    ) -> None:
        assert self.ch is not None
        self.ch.basic_publish(
            exchange=exchange, routing_key=routing_key, body=body, properties=properties
        )

    def consume(
        self,
        queue: str,
        on_message: Callable[..., None],
        auto_ack: bool = False,
    ) -> None:
        assert self.ch is not None
        self.ch.basic_consume(queue=queue, on_message_callback=on_message, auto_ack=auto_ack)

    def ack(self, delivery_tag: int) -> None:
        assert self.ch is not None
        self.ch.basic_ack(delivery_tag)

    async def close(self) -> None:
        if self.conn is None or self.conn.is_closed:
            return
        self.conn.close()
        try:
            await asyncio.wait_for(self._closed.wait(), timeout=5)
        except TimeoutError:
            pass


async def run_raw_publish_consume(
    *,
    payload_bytes: int,
    concurrency: int,
    message_count: int,
) -> BenchResult:
    queue = f"pk.aio.raw.{uuid.uuid4().hex}"
    body = make_payload(payload_bytes)
    latencies: list[float] = []
    received = 0
    done = asyncio.Event()
    loop = asyncio.get_running_loop()

    cons = await _AioConn().connect()
    await cons.queue_declare(queue, auto_delete=True)

    measuring = False
    warmup_done = asyncio.Event()

    def on_message(ch, method, properties, _body_in):  # type: ignore[no-untyped-def]
        nonlocal received
        headers = properties.headers or {}
        t0_us = headers.get("t0_us")
        if measuring and isinstance(t0_us, int):
            latencies.append(loop.time() - (t0_us / 1_000_000))
        ch.basic_ack(method.delivery_tag)
        if not measuring:
            warmup_done.set()
            return
        received += 1
        if received >= message_count:
            done.set()

    cons.consume(queue, on_message)

    publishers: list[_AioConn] = []
    per = message_count // concurrency
    rem = message_count % concurrency
    for _ in range(concurrency):
        publishers.append(await _AioConn().connect())

    publishers[0].publish("", queue, body)
    await asyncio.wait_for(warmup_done.wait(), timeout=30)
    measuring = True

    async def publish_worker(pub: _AioConn, n: int) -> None:
        for _ in range(n):
            t0_us = int(loop.time() * 1_000_000)
            pub.publish(
                "",
                queue,
                body,
                pika.BasicProperties(headers={"t0_us": t0_us}),
            )
            # Yield so consume callbacks can run on this loop (nuropb awaits drain).
            await asyncio.sleep(0)

    with Stopwatch() as sw:
        await asyncio.gather(
            *[
                publish_worker(publishers[i], per + (1 if i < rem else 0))
                for i in range(concurrency)
            ]
        )
        await asyncio.wait_for(done.wait(), timeout=max(30.0, message_count * 0.01))

    for p in publishers:
        await p.close()
    await cons.close()

    p50, p99 = summarize_latencies_ms(latencies)
    return BenchResult(
        library="pika",
        scenario="raw_publish_consume",
        payload_bytes=payload_bytes,
        concurrency=concurrency,
        message_count=message_count,
        wall_seconds=sw.elapsed,
        msgs_per_sec=timed_msgs_per_sec(message_count, sw.elapsed),
        latency_p50_ms=p50,
        latency_p99_ms=p99,
        notes="AsyncioConnection",
    )


async def run_rpc_exclusive(
    *,
    payload_bytes: int,
    concurrency: int,
    message_count: int,
) -> BenchResult:
    req_q = f"pk.aio.rpc.{uuid.uuid4().hex}"
    payload = make_payload(payload_bytes)
    latencies: list[float] = []
    srv = await _AioConn().connect()
    await srv.queue_declare(req_q, auto_delete=True)

    def on_req(ch, method, properties, _body):  # type: ignore[no-untyped-def]
        reply_to = properties.reply_to
        corr = properties.correlation_id
        if reply_to and corr:
            ch.basic_publish(
                exchange="",
                routing_key=reply_to,
                body=b'{"jsonrpc":"2.0","result":{"ok":true},"id":"' + corr.encode() + b'"}',
                properties=pika.BasicProperties(correlation_id=corr),
            )
        ch.basic_ack(method.delivery_tag)

    srv.consume(req_q, on_req)

    per = message_count // concurrency
    rem = message_count % concurrency
    clients: list[tuple[_AioConn, str, dict[str, asyncio.Future[None]]]] = []
    loop = asyncio.get_running_loop()

    async def setup_client() -> tuple[_AioConn, str, dict[str, asyncio.Future[None]]]:
        cli = await _AioConn().connect()
        declared = await cli.queue_declare("", exclusive=True, auto_delete=True)
        reply_q = declared.method.queue
        pending: dict[str, asyncio.Future[None]] = {}

        def on_reply(ch, method, properties, _body):  # type: ignore[no-untyped-def]
            cid = properties.correlation_id
            fut = pending.pop(cid, None)
            if fut is not None and not fut.done():
                fut.set_result(None)
            ch.basic_ack(method.delivery_tag)

        cli.consume(reply_q, on_reply)
        return cli, reply_q, pending

    async def one_rpc(
        cli: _AioConn,
        reply_q: str,
        pending: dict[str, asyncio.Future[None]],
        *,
        timed: bool,
    ) -> None:
        cid = uuid.uuid4().hex
        fut: asyncio.Future[None] = loop.create_future()
        pending[cid] = fut
        t0 = time.perf_counter()
        cli.publish(
            "",
            req_q,
            payload,
            pika.BasicProperties(reply_to=reply_q, correlation_id=cid),
        )
        await fut
        if timed:
            latencies.append(time.perf_counter() - t0)

    for _ in range(concurrency):
        clients.append(await setup_client())
    for cli, reply_q, pending in clients:
        await one_rpc(cli, reply_q, pending, timed=False)

    async def client_worker(
        cli: _AioConn,
        reply_q: str,
        pending: dict[str, asyncio.Future[None]],
        n: int,
    ) -> None:
        for _ in range(n):
            await one_rpc(cli, reply_q, pending, timed=True)

    try:
        with Stopwatch() as sw:
            await asyncio.gather(
                *[
                    client_worker(
                        clients[i][0],
                        clients[i][1],
                        clients[i][2],
                        per + (1 if i < rem else 0),
                    )
                    for i in range(concurrency)
                ]
            )
    finally:
        for cli, _q, _p in clients:
            await cli.close()
        await srv.close()

    p50, p99 = summarize_latencies_ms(latencies)
    return BenchResult(
        library="pika",
        scenario="rpc_exclusive_reply",
        payload_bytes=payload_bytes,
        concurrency=concurrency,
        message_count=message_count,
        wall_seconds=sw.elapsed,
        msgs_per_sec=timed_msgs_per_sec(message_count, sw.elapsed),
        latency_p50_ms=p50,
        latency_p99_ms=p99,
        notes="AsyncioConnection exclusive reply queue",
    )


async def run_rpc_direct_reply_to(
    *,
    payload_bytes: int,
    concurrency: int,
    message_count: int,
) -> BenchResult:
    req_q = f"pk.aio.drep.{uuid.uuid4().hex}"
    payload = make_payload(payload_bytes)
    latencies: list[float] = []
    srv = await _AioConn().connect()
    await srv.queue_declare(req_q, auto_delete=True)

    def on_req(ch, method, properties, _body):  # type: ignore[no-untyped-def]
        reply_to = properties.reply_to
        corr = properties.correlation_id
        if reply_to and corr:
            ch.basic_publish(
                exchange="",
                routing_key=reply_to,
                body=b'{"ok":true}',
                properties=pika.BasicProperties(correlation_id=corr),
            )
        ch.basic_ack(method.delivery_tag)

    srv.consume(req_q, on_req)

    per = message_count // concurrency
    rem = message_count % concurrency
    clients: list[tuple[_AioConn, dict[str, asyncio.Future[None]]]] = []
    loop = asyncio.get_running_loop()

    async def setup_client() -> tuple[_AioConn, dict[str, asyncio.Future[None]]]:
        cli = await _AioConn().connect()
        pending: dict[str, asyncio.Future[None]] = {}

        def on_reply(_ch, _method, properties, _body):  # type: ignore[no-untyped-def]
            cid = properties.correlation_id
            fut = pending.pop(cid, None)
            if fut is not None and not fut.done():
                fut.set_result(None)

        cli.consume("amq.rabbitmq.reply-to", on_reply, auto_ack=True)
        return cli, pending

    async def one_rpc(
        cli: _AioConn, pending: dict[str, asyncio.Future[None]], *, timed: bool
    ) -> None:
        cid = uuid.uuid4().hex
        fut: asyncio.Future[None] = loop.create_future()
        pending[cid] = fut
        t0 = time.perf_counter()
        cli.publish(
            "",
            req_q,
            payload,
            pika.BasicProperties(reply_to="amq.rabbitmq.reply-to", correlation_id=cid),
        )
        await fut
        if timed:
            latencies.append(time.perf_counter() - t0)

    for _ in range(concurrency):
        clients.append(await setup_client())
    for cli, pending in clients:
        await one_rpc(cli, pending, timed=False)

    async def client_worker(
        cli: _AioConn, pending: dict[str, asyncio.Future[None]], n: int
    ) -> None:
        for _ in range(n):
            await one_rpc(cli, pending, timed=True)

    try:
        with Stopwatch() as sw:
            await asyncio.gather(
                *[
                    client_worker(clients[i][0], clients[i][1], per + (1 if i < rem else 0))
                    for i in range(concurrency)
                ]
            )
    finally:
        for cli, _p in clients:
            await cli.close()
        await srv.close()

    p50, p99 = summarize_latencies_ms(latencies)
    return BenchResult(
        library="pika",
        scenario="rpc_direct_reply_to",
        payload_bytes=payload_bytes,
        concurrency=concurrency,
        message_count=message_count,
        wall_seconds=sw.elapsed,
        msgs_per_sec=timed_msgs_per_sec(message_count, sw.elapsed),
        latency_p50_ms=p50,
        latency_p99_ms=p99,
        notes="AsyncioConnection amq.rabbitmq.reply-to",
    )


async def run_event_fanout(
    *,
    payload_bytes: int,
    concurrency: int,
    message_count: int,
    subscribers: int = 1,
) -> BenchResult:
    exchange = f"pk.aio.fanout.{uuid.uuid4().hex}"
    body = make_payload(payload_bytes)
    target = message_count * subscribers
    needed = subscribers
    received = 0
    done = asyncio.Event()
    subs: list[_AioConn] = []

    async def start_sub() -> None:
        nonlocal received
        conn = await _AioConn().connect()
        subs.append(conn)
        await conn.exchange_declare(
            exchange, exchange_type=ExchangeType.fanout, auto_delete=True
        )
        declared = await conn.queue_declare("", exclusive=True, auto_delete=True)
        q = declared.method.queue
        await conn.queue_bind(q, exchange)

        def on_msg(ch, method, _properties, _body_in):  # type: ignore[no-untyped-def]
            nonlocal received
            ch.basic_ack(method.delivery_tag)
            received += 1
            if received >= needed:
                done.set()

        conn.consume(q, on_msg)

    for _ in range(subscribers):
        await start_sub()

    publishers: list[_AioConn] = []
    per = message_count // concurrency
    rem = message_count % concurrency
    for _ in range(concurrency):
        pub = await _AioConn().connect()
        await pub.exchange_declare(
            exchange, exchange_type=ExchangeType.fanout, auto_delete=True
        )
        publishers.append(pub)

    async def publish_worker(pub: _AioConn, n: int) -> None:
        for _ in range(n):
            pub.publish(exchange, "", body)
            await asyncio.sleep(0)

    try:
        publishers[0].publish(exchange, "", body)
        await asyncio.wait_for(done.wait(), timeout=30.0)
        received = 0
        done.clear()
        needed = target
        with Stopwatch() as sw:
            await asyncio.gather(
                *[
                    publish_worker(publishers[i], per + (1 if i < rem else 0))
                    for i in range(concurrency)
                ]
            )
            await asyncio.wait_for(done.wait(), timeout=max(30.0, message_count * 0.02))
    finally:
        for p in publishers:
            await p.close()
        for s in subs:
            await s.close()

    return BenchResult(
        library="pika",
        scenario="event_fanout",
        payload_bytes=payload_bytes,
        concurrency=concurrency,
        message_count=message_count,
        wall_seconds=sw.elapsed,
        msgs_per_sec=timed_msgs_per_sec(message_count, sw.elapsed),
        notes=f"AsyncioConnection subscribers={subscribers}",
        extra={"subscribers": subscribers, "deliveries": target},
    )
