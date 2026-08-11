"""Shared config for the vanilla topic pub/sub example."""

from __future__ import annotations

import os

from nuropb_rmq import ConnectionConfig

EXCHANGE = "nr.ex.logs"
# Default binding matches all log severities under logs.*
DEFAULT_BINDING_KEY = "logs.*"
SAMPLE_MESSAGES = (
    ("logs.info", b"info: started"),
    ("logs.error", b"error: boom"),
    ("logs.debug", b"debug: detail"),
)


def cfg() -> ConnectionConfig:
    return ConnectionConfig(
        host=os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1"),
        port=int(os.environ.get("NUROPB_RMQ_PORT", "5672")),
        username=os.environ.get("NUROPB_RMQ_USER", "guest"),
        password=os.environ.get("NUROPB_RMQ_PASSWORD", "guest"),
    )
