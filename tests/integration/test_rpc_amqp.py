# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Integration: JSON-RPC request/reply and DLQ timeout over AMQP."""

from __future__ import annotations

import asyncio
import os
import socket
import uuid

import pytest

from nuropb_rmq.patterns.dlq_timeout import DlqTimeoutProcessor
from nuropb_rmq.patterns.errors import REQUEST_TIMEOUT, RpcError
from nuropb_rmq.patterns.rpc import RpcClient, RpcServer
from nuropb_rmq.session.session import Session
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig


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


async def _declare_ttl_request_queue(queue: str, dlx: str, dlq: str, ttl_ms: int) -> None:
    conn = AmqpConnection(_cfg())
    await conn.connect()
    ch = await conn.open_channel(1)
    await conn.exchange_declare(ch, dlx, exchange_type="fanout", durable=True, auto_delete=False)
    await conn.queue_declare(ch, dlq, durable=True, auto_delete=False)
    await conn.queue_bind(ch, dlq, dlx)
    await conn.queue_declare(
        ch,
        queue,
        durable=True,
        auto_delete=False,
        arguments={"x-message-ttl": ttl_ms, "x-dead-letter-exchange": dlx},
    )
    await conn.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rpc_request_reply() -> None:
    q = f"nr.rpc.{uuid.uuid4().hex}"

    async def handler(method: str, params: object) -> object:
        assert method == "echo.ping"
        assert isinstance(params, dict)
        return {"pong": params.get("n")}

    server = RpcServer(_cfg(), queue=q, handler=handler)
    session = Session(_cfg())
    try:
        await server.start()
        await session.start()
        client = RpcClient(session)
        result = await client.request(q, "echo.ping", {"n": 7})
        assert result == {"pong": 7}
    finally:
        await session.close()
        await server.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rpc_dlq_timeout() -> None:
    suffix = uuid.uuid4().hex
    q = f"nr.rpc.ttl.{suffix}"
    dlx = f"nr.dlx.{suffix}"
    dlq = f"nr.dlq.{suffix}"
    await _declare_ttl_request_queue(q, dlx, dlq, ttl_ms=500)

    # Server that never consumes — messages expire to DLQ
    session = Session(_cfg())
    dlq_proc = DlqTimeoutProcessor(_cfg(), dlq_name=dlq)
    # Pre-declare request queue already done; RpcServer would redeclare without TTL —
    # so we do not start a service consumer.
    try:
        await dlq_proc.start()
        await session.start()
        client = RpcClient(session)
        with pytest.raises(RpcError) as ei:
            await asyncio.wait_for(client.request(q, "slow.op", {}), timeout=10)
        assert ei.value.code == REQUEST_TIMEOUT
    finally:
        await session.close()
        await dlq_proc.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dlq_unroutable_when_reply_queue_gone() -> None:
    suffix = uuid.uuid4().hex
    q = f"nr.rpc.ttl.gone.{suffix}"
    dlx = f"nr.dlx.gone.{suffix}"
    dlq = f"nr.dlq.gone.{suffix}"
    await _declare_ttl_request_queue(q, dlx, dlq, ttl_ms=400)
    session = Session(_cfg())
    dlq_proc = DlqTimeoutProcessor(_cfg(), dlq_name=dlq)
    try:
        await dlq_proc.start()
        await session.start()
        client = RpcClient(session)
        req = asyncio.create_task(client.request(q, "slow.op", {}))
        await asyncio.sleep(0.05)
        await session.close()
        with pytest.raises(Exception):
            await asyncio.wait_for(req, timeout=5)
        for _ in range(40):
            if dlq_proc.unroutable_replies >= 1:
                break
            await asyncio.sleep(0.1)
        assert dlq_proc.unroutable_replies >= 1
    finally:
        await dlq_proc.close()
