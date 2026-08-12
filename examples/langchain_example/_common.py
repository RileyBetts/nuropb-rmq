# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Shared config and names for the LangChain mesh service-tool example."""

from __future__ import annotations

import os
from pathlib import Path

from nuropb_rmq import DEFAULT_MESH_EXCHANGE, ConnectionConfig

SERVICE_NAME = "orders"
METHODS = ("get_status",)
MESH_EXCHANGE = DEFAULT_MESH_EXCHANGE
TOOL_DESCRIPTION = (
    "Look up the status of a customer order by order_id "
    "(e.g. ORD-1001). Returns status, carrier, eta, and tracking when available."
)

_ENV_PATH = Path(__file__).resolve().parent / ".env"


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from .env into os.environ if not already set.

    Shell / process env wins. No python-dotenv dependency.
    """
    env_file = path or _ENV_PATH
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value


def cfg() -> ConnectionConfig:
    return ConnectionConfig(
        host=os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1"),
        port=int(os.environ.get("NUROPB_RMQ_PORT", "5672")),
        username=os.environ.get("NUROPB_RMQ_USER", "guest"),
        password=os.environ.get("NUROPB_RMQ_PASSWORD", "guest"),
    )


def routing_key(method: str) -> str:
    """Mesh routing key / JSON-RPC method name: ``orders.get_status``."""
    if method.startswith(f"{SERVICE_NAME}."):
        return method
    return f"{SERVICE_NAME}.{method}"
