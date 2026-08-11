"""AMQPS mTLS smoke: tls-verify-full + SASL EXTERNAL against a local broker.

Opt-in — skipped unless ``NUROPB_RMQ_MTLS=1`` and CA/client cert files plus
port 5671 are available. See ``scripts/gen_amqps_certs.sh`` and
``scripts/rabbitmq-amqps-mtls.conf.example``.
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
_DEFAULT_CERT = _REPO / "dev" / "amqps" / "client.pem"
_DEFAULT_KEY = _REPO / "dev" / "amqps" / "client.key"


def _mtls_ready() -> tuple[str, int, str, str, str, str] | None:
    if os.environ.get("NUROPB_RMQ_MTLS", "").strip() not in {"1", "true", "yes"}:
        return None
    ca = os.environ.get("NUROPB_RMQ_CA_FILE", str(_DEFAULT_CA))
    cert = os.environ.get("NUROPB_RMQ_CERT_FILE", str(_DEFAULT_CERT))
    key = os.environ.get("NUROPB_RMQ_KEY_FILE", str(_DEFAULT_KEY))
    if not all(Path(p).is_file() for p in (ca, cert, key)):
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
    return host, port, ca, cert, key, hostname


@pytest.mark.integration
@pytest.mark.asyncio
async def test_amqps_mtls_external_publish_consume_ack() -> None:
    ready = _mtls_ready()
    if ready is None:
        pytest.skip(
            "mTLS not enabled (set NUROPB_RMQ_MTLS=1, client certs, broker verify_peer)"
        )
    host, port, ca, cert, key, server_hostname = ready
    conn = AmqpConnection(
        ConnectionConfig(
            host=host,
            port=port,
            # Username unused when EXTERNAL succeeds; kept for PLAIN fallback clarity.
            username="nuropb-client",
            password="",
            tls=True,
            tls_profile=TlsProfile.VERIFY_FULL,
            ca_file=ca,
            cert_file=cert,
            key_file=key,
            server_hostname=server_hostname,
        )
    )
    try:
        await conn.connect()
        assert conn.sm.state == ConnState.OPEN_OK
        assert conn.config.cert_file
        ch = await conn.open_channel(1)
        queue = await conn.queue_declare(ch, queue="", exclusive=True, auto_delete=True)
        await conn.basic_consume(ch, queue)
        body = b"amqps-mtls-external"
        await conn.basic_publish(
            ch, body, routing_key=queue, properties={"content_type": "text/plain"}
        )
        msg = await conn.receive(timeout=5)
        assert msg.body == body
        await conn.basic_ack(ch, msg.delivery_tag)
    finally:
        await conn.close()
