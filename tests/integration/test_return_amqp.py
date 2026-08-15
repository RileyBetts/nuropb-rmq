# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Integration: mandatory publish / basic.return and connection.update-secret."""

from __future__ import annotations

import os
import socket
import uuid

import pytest

from nuropb_rmq import (
    AmqpConnection,
    ConnectionConfig,
    PublishReturned,
    RpcClient,
    RpcError,
    Session,
)
from nuropb_rmq.patterns.errors import PUBLISH_RETURNED


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
async def test_mandatory_unroutable_raises_publish_returned() -> None:
    cfg = _cfg()
    conn = AmqpConnection(cfg)
    missing = f"nr.test.missing.{uuid.uuid4().hex[:8]}"
    try:
        await conn.connect()
        ch = await conn.open_channel(1)
        with pytest.raises(PublishReturned) as excinfo:
            await conn.basic_publish(
                ch,
                b"no-route",
                routing_key=missing,
                properties={"content_type": "text/plain", "app_id": "nuropb-rmq"},
                confirm=True,
                mandatory=True,
            )
        err = excinfo.value
        assert err.reply_code == 312
        assert err.routing_key == missing
        assert err.body == b"no-route"
        assert err.properties.get("app_id") == "nuropb-rmq"
    finally:
        await conn.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mandatory_false_unroutable_is_silent() -> None:
    cfg = _cfg()
    conn = AmqpConnection(cfg)
    missing = f"nr.test.silent.{uuid.uuid4().hex[:8]}"
    try:
        await conn.connect()
        ch = await conn.open_channel(1)
        await conn.basic_publish(
            ch,
            b"dropped",
            routing_key=missing,
            confirm=True,
            mandatory=False,
        )
        with pytest.raises(TimeoutError):
            await conn.receive_return(timeout=0.4)
    finally:
        await conn.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_content_properties_roundtrip_live() -> None:
    cfg = _cfg()
    conn = AmqpConnection(cfg)
    queue = f"nr.test.props.{uuid.uuid4().hex[:8]}"
    try:
        await conn.connect()
        ch = await conn.open_channel(1)
        await conn.queue_declare(ch, queue, durable=False, exclusive=True, auto_delete=True)
        await conn.basic_consume(ch, queue)
        await conn.basic_publish(
            ch,
            b"hi",
            routing_key=queue,
            properties={
                "content_type": "text/plain",
                "timestamp": 1_700_000_000,
                "type": "note",
                "user_id": "guest",
                "app_id": "nuropb-rmq",
                "cluster_id": "dev",
            },
            confirm=True,
        )
        msg = await conn.receive(timeout=5)
        assert msg.body == b"hi"
        assert msg.properties["timestamp"] == 1_700_000_000
        assert msg.properties["type"] == "note"
        assert msg.properties["user_id"] == "guest"
        assert msg.properties["app_id"] == "nuropb-rmq"
        assert msg.properties["cluster_id"] == "dev"
        await conn.basic_ack(ch, msg.delivery_tag)
    finally:
        await conn.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rpc_unroutable_mesh_key_is_publish_returned() -> None:
    cfg = _cfg()
    session = Session(cfg)
    try:
        await session.start()
        client = RpcClient(session)
        with pytest.raises(RpcError) as excinfo:
            await client.request(
                f"nr.test.missing.{uuid.uuid4().hex[:8]}",
                "ping",
            )
        assert excinfo.value.code == PUBLISH_RETURNED
    finally:
        await session.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_secret_same_password() -> None:
    cfg = _cfg()
    conn = AmqpConnection(cfg)
    try:
        await conn.connect()
        await conn.update_secret(cfg.password, reason="nuropb-rmq test")
        assert conn.config.password == cfg.password
    finally:
        await conn.close()
