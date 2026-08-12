# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Integration: mesh binding + claims-gated RPC."""

from __future__ import annotations

import os
import socket
import time
import uuid

import pytest

from nuropb_rmq.patterns.errors import CLAIMS_MISSING, RpcError
from nuropb_rmq.patterns.mesh import DEFAULT_MESH_EXCHANGE, MeshService, ServiceIdentity
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
async def test_mesh_rpc_happy_path() -> None:
    svc = f"svc{uuid.uuid4().hex[:8]}"
    exchange = f"nr.mesh.{uuid.uuid4().hex}"

    async def handler(method: str, params: object) -> object:
        assert method == f"{svc}.ping"
        return {"pong": True}

    mesh = MeshService(
        _cfg(),
        identity=ServiceIdentity(svc),
        methods=["ping"],
        exchange=exchange,
    )
    session = Session(_cfg())
    server: RpcServer | None = None
    try:
        await mesh.start()
        server = RpcServer.from_mesh(mesh, handler=handler)
        await server.start()
        await session.start()
        client = RpcClient(session)
        result = await client.request(
            f"{svc}.ping",
            f"{svc}.ping",
            {},
            exchange=exchange,
        )
        assert result == {"pong": True}
    finally:
        await session.close()
        if server:
            await server.close()
        await mesh.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mesh_rpc_auth_required() -> None:
    jwt = pytest.importorskip("jwt")
    from nuropb_rmq.patterns.context import AuthConfig

    svc = f"svc{uuid.uuid4().hex[:8]}"
    exchange = f"nr.mesh.{uuid.uuid4().hex}"
    secret = "integration-secret-key-32bytes!!"

    async def handler(method: str, params: object) -> object:
        return {"ok": True}

    auth = AuthConfig(jwt_secret=secret, algorithms=("HS256",))
    mesh = MeshService(
        _cfg(),
        identity=ServiceIdentity(svc),
        methods=["secure"],
        exchange=exchange,
    )
    session = Session(_cfg())
    server: RpcServer | None = None
    try:
        await mesh.start()
        server = RpcServer.from_mesh(mesh, handler=handler, auth=auth)
        await server.start()
        await session.start()
        client = RpcClient(session)
        with pytest.raises(RpcError) as ei:
            await client.request(
                f"{svc}.secure",
                f"{svc}.secure",
                {},
                exchange=exchange,
            )
        assert ei.value.code == CLAIMS_MISSING

        # Pre-register id so token jti can match
        rid = uuid.uuid4().hex
        token = jwt.encode(
            {
                "jti": rid,
                "method": f"{svc}.secure",
                "exp": int(time.time()) + 120,
            },
            secret,
            algorithm="HS256",
        )
        result = await client.request(
            f"{svc}.secure",
            f"{svc}.secure",
            {},
            exchange=exchange,
            request_id=rid,
            claims_token=token,
        )
        assert result == {"ok": True}
    finally:
        await session.close()
        if server:
            await server.close()
        await mesh.close()


_ = DEFAULT_MESH_EXCHANGE
