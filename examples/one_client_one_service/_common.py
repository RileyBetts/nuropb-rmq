# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Shared config and names for the one-client / one-service example."""

from __future__ import annotations

import os

from nuropb_rmq import (
    DEFAULT_MESH_EXCHANGE,
    DEFAULT_REGISTRY_EXCHANGE,
    ConnectionConfig,
)

SERVICE_NAME = "demo"
METHODS = ("ping", "echo")
EVENTS_EXCHANGE = "nr.demo.events"
MESH_EXCHANGE = DEFAULT_MESH_EXCHANGE
REGISTRY_EXCHANGE = DEFAULT_REGISTRY_EXCHANGE


def cfg() -> ConnectionConfig:
    return ConnectionConfig(
        host=os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1"),
        port=int(os.environ.get("NUROPB_RMQ_PORT", "5672")),
        username=os.environ.get("NUROPB_RMQ_USER", "guest"),
        password=os.environ.get("NUROPB_RMQ_PASSWORD", "guest"),
    )


def routing_key(method: str) -> str:
    """Mesh routing key / JSON-RPC method name: ``demo.ping``."""
    if method.startswith(f"{SERVICE_NAME}."):
        return method
    return f"{SERVICE_NAME}.{method}"
