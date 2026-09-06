# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Integration: JSON-RPC notification pub/sub over fanout and topic."""

from __future__ import annotations

import asyncio
import os
import socket
import uuid

import pytest

from nuropb_rmq.config.queue_profile import durable_classic
from nuropb_rmq.patterns.events import EventPublisher, EventSubscriber
from nuropb_rmq.transport.connection import ConnectionConfig


def _port() -> int:
    if "NUROPB_RMQ_PORT" in os.environ:
        return int(os.environ["NUROPB_RMQ_PORT"])
    for port in (5672, 5673):
        with socket.socket() as s:
            s.settimeout(0.2)
            try:
                s.connect((os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1"), port))
                return port
            except OSError:
                continue
    pytest.skip("RabbitMQ not listening on 5672/5673")


def _cfg() -> ConnectionConfig:
    return ConnectionConfig(
        host=os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1"),
        port=_port(),
        username="guest",
        password="guest",
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_fanout() -> None:
    exchange = f"nr.evt.fanout.{uuid.uuid4().hex}"
    received: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

    async def handler(method: str, params: object, _msg: object) -> None:
        await received.put((method, params))

    pub = EventPublisher(_cfg(), exchange=exchange, exchange_type="fanout")
    sub = EventSubscriber(
        _cfg(),
        exchange=exchange,
        exchange_type="fanout",
        handler=handler,
    )
    try:
        await sub.start()
        await pub.start()
        await pub.publish("", "order.created", {"n": 1})
        method, params = await asyncio.wait_for(received.get(), timeout=5)
        assert method == "order.created"
        assert params == {"n": 1}
    finally:
        await pub.close()
        await sub.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_topic() -> None:
    exchange = f"nr.evt.topic.{uuid.uuid4().hex}"
    received: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

    async def handler(method: str, params: object, _msg: object) -> None:
        await received.put((method, params))

    pub = EventPublisher(_cfg(), exchange=exchange, exchange_type="topic")
    sub = EventSubscriber(
        _cfg(),
        exchange=exchange,
        exchange_type="topic",
        binding_key="orders.#",
        handler=handler,
    )
    try:
        await sub.start()
        await pub.start()
        await pub.publish("orders.created", "order.created", {"sku": "a"})
        method, params = await asyncio.wait_for(received.get(), timeout=5)
        assert method == "order.created"
        assert params == {"sku": "a"}
    finally:
        await pub.close()
        await sub.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_durable_fanout_named_queues() -> None:
    """Each named durable queue gets a copy; offline queue retains."""
    exchange = f"nr.evt.dur.{uuid.uuid4().hex}"
    q_a = f"nr.fix.a.{uuid.uuid4().hex}"
    q_b = f"nr.fix.b.{uuid.uuid4().hex}"
    got_a: asyncio.Queue[str] = asyncio.Queue()
    got_b: asyncio.Queue[str] = asyncio.Queue()

    async def ha(method: str, _p: object, _m: object) -> None:
        await got_a.put(method)

    async def hb(method: str, _p: object, _m: object) -> None:
        await got_b.put(method)

    profile = durable_classic(dead_letter_exchange=f"nr.dlx.{uuid.uuid4().hex[:8]}")
    pub = EventPublisher(
        _cfg(), exchange=exchange, exchange_type="fanout", queue_profile=profile
    )
    sub_a = EventSubscriber(
        _cfg(),
        exchange=exchange,
        exchange_type="fanout",
        queue=q_a,
        durable=True,
        handler=ha,
    )
    sub_b = EventSubscriber(
        _cfg(),
        exchange=exchange,
        exchange_type="fanout",
        queue=q_b,
        durable=True,
        handler=hb,
    )
    try:
        await sub_a.start()
        await sub_b.start()
        await pub.start()
        await pub.publish("", "fix.exec", {"n": 1})
        assert await asyncio.wait_for(got_a.get(), timeout=5) == "fix.exec"
        assert await asyncio.wait_for(got_b.get(), timeout=5) == "fix.exec"
        await sub_a.close()
        await pub.publish("", "fix.exec", {"n": 2})
        assert await asyncio.wait_for(got_b.get(), timeout=5) == "fix.exec"
        sub_a = EventSubscriber(
            _cfg(),
            exchange=exchange,
            exchange_type="fanout",
            queue=q_a,
            durable=True,
            handler=ha,
        )
        await sub_a.start()
        assert await asyncio.wait_for(got_a.get(), timeout=5) == "fix.exec"
    finally:
        await pub.close()
        await sub_a.close()
        await sub_b.close()
