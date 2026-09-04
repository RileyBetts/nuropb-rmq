# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Integration: park-and-retry republishes in-flight RPC after a client drop."""

from __future__ import annotations

import asyncio
import os
import socket
import uuid

import pytest

from nuropb_rmq.patterns.errors import CONNECTION_LOST, RpcError
from nuropb_rmq.patterns.rpc import RpcClient, RpcServer
from nuropb_rmq.session.session import Session
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
async def test_park_and_retry_completes_after_drop() -> None:
    q = f"nr.rpc.park.{uuid.uuid4().hex}"
    calls = 0

    async def handler(method: str, params: object) -> object:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.4)
        assert method == "echo.park"
        return {"pong": 1, "calls": calls}

    server = RpcServer(_cfg(), queue=q, handler=handler)
    session = Session(_cfg())  # default: park-and-retry
    try:
        await server.start()
        await session.start()
        client = RpcClient(session)
        req = asyncio.create_task(client.request(q, "echo.park", {}))
        await asyncio.sleep(0.12)
        await session.conn.force_drop()
        result = await asyncio.wait_for(req, timeout=15)
        assert result["pong"] == 1
        assert session.epoch >= 1
        assert session.reply_queue_open
        assert calls >= 1  # at-least-once: may run twice
    finally:
        await session.close()
        await server.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_park_and_retry_dedup_window_handler_once() -> None:
    q = f"nr.rpc.park.dedup.{uuid.uuid4().hex}"
    calls = 0

    async def handler(method: str, params: object) -> object:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.4)
        assert method == "echo.park"
        return {"pong": 1, "calls": calls}

    server = RpcServer(_cfg(), queue=q, handler=handler, dedup_window=32)
    session = Session(_cfg())
    try:
        await server.start()
        await session.start()
        client = RpcClient(session)
        req = asyncio.create_task(client.request(q, "echo.park", {}))
        await asyncio.sleep(0.12)
        await session.conn.force_drop()
        result = await asyncio.wait_for(req, timeout=15)
        assert result["pong"] == 1
        assert session.epoch >= 1
        assert calls == 1
    finally:
        await session.close()
        await server.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fail_fast_policy_raises_connection_lost() -> None:
    q = f"nr.rpc.ff.{uuid.uuid4().hex}"

    async def handler(method: str, params: object) -> object:
        await asyncio.sleep(2)
        return {}

    server = RpcServer(_cfg(), queue=q, handler=handler)
    session = Session(_cfg(), fail_outstanding=True)
    try:
        await server.start()
        await session.start()
        client = RpcClient(session)
        req = asyncio.create_task(client.request(q, "echo.slow", {}))
        await asyncio.sleep(0.1)
        await session.conn.force_drop()
        with pytest.raises(RpcError) as ei:
            await asyncio.wait_for(req, timeout=5)
        assert ei.value.code == CONNECTION_LOST
    finally:
        await session.close()
        await server.close()
