# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Integration smoke: connect, declare, publish, consume, ack against RabbitMQ."""

from __future__ import annotations

import os
import socket

import pytest

from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig


def _amqp_port() -> int:
    if "NUROPB_RMQ_PORT" in os.environ:
        return int(os.environ["NUROPB_RMQ_PORT"])
    # Prefer standard 5672; fall back to common brew override 5673.
    for port in (5672, 5673):
        with socket.socket() as s:
            s.settimeout(0.2)
            try:
                s.connect((os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1"), port))
                return port
            except OSError:
                continue
    pytest.skip("RabbitMQ not listening on 5672/5673")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_publish_consume_ack() -> None:
    host = os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1")
    port = _amqp_port()
    conn = AmqpConnection(
        ConnectionConfig(host=host, port=port, username="guest", password="guest")
    )
    try:
        await conn.connect()
        ch = await conn.open_channel(1)
        queue = await conn.queue_declare(ch, queue="", exclusive=True, auto_delete=True)
        await conn.basic_consume(ch, queue)
        body = b"hello-nuropb-rmq"
        await conn.basic_publish(
            ch, body, routing_key=queue, properties={"content_type": "text/plain"}
        )
        msg = await conn.receive(timeout=5)
        assert msg.body == body
        assert msg.routing_key == queue
        await conn.basic_ack(ch, msg.delivery_tag)
    finally:
        await conn.close()
