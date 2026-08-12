# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Shared config and names for the LangGraph invoice extraction example."""

from __future__ import annotations

import os

from nuropb_rmq import DEFAULT_MESH_EXCHANGE, ConnectionConfig

SERVICE_NAME = "invoices"
METHODS = ("extract",)
MESH_EXCHANGE = DEFAULT_MESH_EXCHANGE
EXTRACT_READS = ("document_id", "raw_text", "doc_type")
EXTRACT_WRITES = ("vendor", "invoice_date", "total", "currency", "line_items")


def cfg() -> ConnectionConfig:
    return ConnectionConfig(
        host=os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1"),
        port=int(os.environ.get("NUROPB_RMQ_PORT", "5672")),
        username=os.environ.get("NUROPB_RMQ_USER", "guest"),
        password=os.environ.get("NUROPB_RMQ_PASSWORD", "guest"),
    )


def routing_key(method: str) -> str:
    """Mesh routing key / JSON-RPC method name: ``invoices.extract``."""
    if method.startswith(f"{SERVICE_NAME}."):
        return method
    return f"{SERVICE_NAME}.{method}"
