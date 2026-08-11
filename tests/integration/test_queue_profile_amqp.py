"""Integration: default durable-at-least-once (quorum) work queues."""

from __future__ import annotations

import os
import socket
import uuid

import pytest

from nuropb_rmq.config.queue_profile import DURABLE_AT_LEAST_ONCE
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
async def test_rpc_quorum_durable_at_least_once_roundtrip() -> None:
    """Default RpcServer profile declares quorum + persistent publish succeeds."""
    assert DURABLE_AT_LEAST_ONCE.queue_type == "quorum"
    assert DURABLE_AT_LEAST_ONCE.declare_arguments()["x-queue-type"] == "quorum"
    q = f"nr.rpc.quorum.{uuid.uuid4().hex}"

    async def handler(method: str, params: object) -> object:
        return {"ok": True, "method": method}

    server = RpcServer(_cfg(), queue=q, handler=handler)
    session = Session(_cfg())
    try:
        await server.start()
        assert server.queue_profile.queue_type == "quorum"
        await session.start()
        client = RpcClient(session)
        result = await client.request(q, "quorum.ping", {})
        assert result == {"ok": True, "method": "quorum.ping"}
    finally:
        await session.close()
        await server.close()
