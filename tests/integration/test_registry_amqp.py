"""Integration: mesh registry discovery fanout."""

from __future__ import annotations

import asyncio
import os
import socket
import uuid

import pytest

from nuropb_rmq.patterns.mesh import MeshService, ServiceIdentity
from nuropb_rmq.patterns.registry import MeshRegistryViewer
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
async def test_mesh_announce_visible_to_viewer() -> None:
    registry_ex = f"nr.mesh.registry.{uuid.uuid4().hex}"
    service = f"svc{uuid.uuid4().hex[:8]}"
    viewer = MeshRegistryViewer(_cfg(), registry_exchange=registry_ex)
    mesh = MeshService(
        _cfg(),
        identity=ServiceIdentity(service),
        methods=["ping"],
        announce=True,
        registry_exchange=registry_ex,
        announce_ttl_s=30.0,
        instance_id="itest-1",
    )
    try:
        await viewer.start()
        await mesh.start()
        deadline = asyncio.get_running_loop().time() + 5
        advert = None
        while asyncio.get_running_loop().time() < deadline:
            advert = viewer.lookup(service)
            if advert is not None:
                break
            await asyncio.sleep(0.05)
        assert advert is not None
        assert advert.service == service
        assert advert.methods == ("ping",)
        assert advert.instance_id == "itest-1"
        assert advert.queue == f"nr.svc.{service}"
    finally:
        await mesh.close()
        await viewer.close()
