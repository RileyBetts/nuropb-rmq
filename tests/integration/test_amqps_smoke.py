# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""AMQPS integration smoke: tls-verify-full against a local SSL listener.

Opt-in — skipped unless ``NUROPB_RMQ_TLS=1`` and a CA file + port 5671 are
available. Generate certs with ``scripts/gen_amqps_certs.sh`` and point the
broker at ``dev/amqps/`` (see README).
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from nuropb_rmq.protocol.connection_sm import ConnState
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig, TlsProfile

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CA = _REPO / "dev" / "amqps" / "ca.pem"


def _amqps_ready() -> tuple[str, int, str, str] | None:
    if os.environ.get("NUROPB_RMQ_TLS", "").strip() not in {"1", "true", "yes"}:
        return None
    ca = os.environ.get("NUROPB_RMQ_CA_FILE", str(_DEFAULT_CA))
    if not Path(ca).is_file():
        return None
    host = os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1")
    port = int(os.environ.get("NUROPB_RMQ_PORT", "5671"))
    with socket.socket() as s:
        s.settimeout(0.3)
        try:
            s.connect((host, port))
        except OSError:
            return None
    hostname = os.environ.get("NUROPB_RMQ_SERVER_HOSTNAME", "localhost")
    return host, port, ca, hostname


@pytest.mark.integration
@pytest.mark.asyncio
async def test_amqps_verify_full_publish_consume_ack() -> None:
    ready = _amqps_ready()
    if ready is None:
        pytest.skip(
            "AMQPS not enabled (set NUROPB_RMQ_TLS=1, CA file, broker SSL on 5671)"
        )
    host, port, ca, server_hostname = ready
    conn = AmqpConnection(
        ConnectionConfig(
            host=host,
            port=port,
            username="guest",
            password="guest",
            tls=True,
            tls_profile=TlsProfile.VERIFY_FULL,
            ca_file=ca,
            server_hostname=server_hostname,
        )
    )
    try:
        await conn.connect()
        assert conn.sm.state == ConnState.OPEN_OK
        assert conn.config.tls_profile == TlsProfile.VERIFY_FULL
        ch = await conn.open_channel(1)
        queue = await conn.queue_declare(ch, queue="", exclusive=True, auto_delete=True)
        await conn.basic_consume(ch, queue)
        body = b"amqps-verify-full"
        await conn.basic_publish(
            ch, body, routing_key=queue, properties={"content_type": "text/plain"}
        )
        msg = await conn.receive(timeout=5)
        assert msg.body == body
        await conn.basic_ack(ch, msg.delivery_tag)
    finally:
        await conn.close()
