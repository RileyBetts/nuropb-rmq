"""Integration: JSON-RPC notification pub/sub over fanout and topic."""

from __future__ import annotations

import asyncio
import os
import socket
import uuid

import pytest

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
