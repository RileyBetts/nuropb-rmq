# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Integration: reconnect Session + mesh rebind after disconnect."""

from __future__ import annotations

import asyncio
import os
import socket
import uuid

import pytest

from nuropb_rmq.patterns.mesh import MeshService, ServiceIdentity
from nuropb_rmq.patterns.rpc import RpcClient, RpcServer
from nuropb_rmq.session.reconnect import ReconnectCoordinator
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
async def test_reconnect_then_mesh_rpc() -> None:
    svc = f"svc{uuid.uuid4().hex[:8]}"
    exchange = f"nr.mesh.{uuid.uuid4().hex}"

    async def handler(method: str, params: object) -> object:
        return {"ok": params}

    mesh = MeshService(
        _cfg(),
        identity=ServiceIdentity(svc),
        methods=["ping"],
        exchange=exchange,
    )
    session = Session(_cfg())  # default: park-and-retry
    server: RpcServer | None = None
    try:
        await mesh.start()
        server = RpcServer.from_mesh(mesh, handler=handler)
        await server.start()
        await session.start()
        client = RpcClient(session)
        assert await client.request(
            f"{svc}.ping", f"{svc}.ping", {"n": 1}, exchange=exchange
        ) == {"ok": {"n": 1}}

        # Client session parks and auto-reconnects. Mesh/RpcServer stay caller-owned.
        await session.conn.force_drop()
        deadline = asyncio.get_running_loop().time() + 10
        while asyncio.get_running_loop().time() < deadline:
            if session.epoch >= 1 and session.reply_queue_open:
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("session did not park-and-retry reconnect after drop")

        await server.close()
        await ReconnectCoordinator().reconnect(session)
        await mesh.rebind()
        server = RpcServer.from_mesh(mesh, handler=handler)
        await server.start()
        client = RpcClient(session)
        assert await client.request(
            f"{svc}.ping", f"{svc}.ping", {"n": 2}, exchange=exchange
        ) == {"ok": {"n": 2}}
        assert session.epoch >= 1
    finally:
        await session.close()
        if server:
            await server.close()
        await mesh.close()
