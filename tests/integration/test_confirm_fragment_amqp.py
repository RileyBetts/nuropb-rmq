# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Integration: large body fragmentation + publisher confirms + cancel/nack."""

from __future__ import annotations

import os
import socket
import uuid

import pytest

from nuropb_rmq import AmqpConnection, ConnectionConfig, durable_at_least_once
from nuropb_rmq.transport.frame import DEFAULT_FRAME_MAX


def _port() -> int:
    if "NUROPB_RMQ_PORT" in os.environ:
        return int(os.environ["NUROPB_RMQ_PORT"])
    for port in (5672, 5673):
        try:
            with socket.create_connection(
                (os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1"), port), timeout=0.3
            ):
                return port
        except OSError:
            continue
    pytest.skip("RabbitMQ not available")


def _cfg() -> ConnectionConfig:
    return ConnectionConfig(
        host=os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1"),
        port=_port(),
        username=os.environ.get("NUROPB_RMQ_USER", "guest"),
        password=os.environ.get("NUROPB_RMQ_PASSWORD", "guest"),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_large_body_roundtrip_and_confirms() -> None:
    cfg = _cfg()
    conn = AmqpConnection(cfg)
    queue = f"nr.test.large.{uuid.uuid4().hex[:8]}"
    body = os.urandom(DEFAULT_FRAME_MAX + 50_000)  # forces multi-frame body
    try:
        await conn.connect()
        ch = await conn.open_channel(1)
        await conn.queue_declare(ch, queue, durable=False, exclusive=True, auto_delete=True)
        await conn.basic_consume(ch, queue)
        await conn.basic_publish(
            ch,
            body,
            routing_key=queue,
            properties={"delivery_mode": 1},
            confirm=True,
        )
        msg = await conn.receive(timeout=10)
        assert msg.body == body
        await conn.basic_ack(ch, msg.delivery_tag)
    finally:
        try:
            await conn.close()
        except Exception:
            pass


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_stops_consumer() -> None:
    cfg = _cfg()
    conn = AmqpConnection(cfg)
    queue = f"nr.test.cancel.{uuid.uuid4().hex[:8]}"
    try:
        await conn.connect()
        ch = await conn.open_channel(1)
        await conn.queue_declare(ch, queue, durable=False, exclusive=True, auto_delete=True)
        tag = await conn.basic_consume(ch, queue)
        await conn.basic_cancel(ch, tag)
        await conn.basic_publish(ch, b"x", routing_key=queue, confirm=False)
        with pytest.raises(TimeoutError):
            await conn.receive(timeout=0.5)
    finally:
        try:
            await conn.close()
        except Exception:
            pass


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nack_to_dlx() -> None:
    cfg = _cfg()
    conn = AmqpConnection(cfg)
    q = f"nr.test.nack.{uuid.uuid4().hex[:8]}"
    dlx = f"nr.dlx.{q}"
    dlq = f"{q}.dlq"
    profile = durable_at_least_once(
        message_ttl_ms=60_000,
        dead_letter_exchange=dlx,
        dead_letter_routing_key="timeout",
        delivery_limit=10,
    )
    try:
        await conn.connect()
        ch = await conn.open_channel(1)
        await conn.queue_declare_profile(ch, q, profile, auto_delete=False)
        await conn.exchange_declare(ch, dlx, exchange_type="topic", durable=True)
        await conn.queue_declare(ch, dlq, durable=True)
        await conn.queue_bind(ch, dlq, dlx, routing_key="timeout")
        await conn.basic_publish(
            ch,
            b"poison",
            routing_key=q,
            queue_profile=profile,
        )
        await conn.basic_consume(ch, q)
        msg = await conn.receive(timeout=5)
        await conn.basic_nack(ch, msg.delivery_tag, requeue=False)
        await conn.basic_consume(ch, dlq)
        dead = await conn.receive(timeout=5)
        assert dead.body == b"poison"
        await conn.basic_ack(ch, dead.delivery_tag)
    finally:
        await conn.close()
