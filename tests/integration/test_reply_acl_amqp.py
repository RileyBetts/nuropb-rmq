# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Live broker correspondence for Lean ``reply-publish-restricted``.

Creates management-API users matching the tightened profile: a client must not
publish to ``nr.reply.*`` via the default exchange; a service user may.

RabbitMQ maps the nameless default exchange to ``amq.default`` for write
checks (not the routing key). ACCESS_REFUSED is ``channel.close`` 403 — the
client must wait for that frame; fire-and-forget publish returns before it.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import urllib.error
import urllib.request
import uuid

import pytest

from nuropb_rmq.protocol import methods as m
from nuropb_rmq.protocol.connection_sm import ProtocolError
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig


def _amqp_port() -> int:
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
    pytest.skip("RabbitMQ AMQP not listening")


def _mgmt_base() -> str | None:
    host = os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1")
    port = int(os.environ.get("NUROPB_RMQ_MGMT_PORT", "15672"))
    with socket.socket() as s:
        s.settimeout(0.3)
        try:
            s.connect((host, port))
        except OSError:
            return None
    return f"http://{host}:{port}"


def _mgmt(method: str, path: str, body: dict | None = None) -> None:
    base = _mgmt_base()
    if base is None:
        pytest.skip("RabbitMQ management API not listening on 15672")
    user = os.environ.get("NUROPB_RMQ_USER", "guest")
    password = os.environ.get("NUROPB_RMQ_PASSWORD", "guest")
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        pytest.skip(f"management API {method} {path} failed: {exc.code}")


async def _forge_denied_service_allowed(
    client_perms: dict[str, str],
    svc_perms: dict[str, str],
) -> None:
    if _mgmt_base() is None:
        pytest.skip("RabbitMQ management API not listening on 15672")
    suffix = uuid.uuid4().hex[:8]
    client_user = f"nr.acl.client.{suffix}"
    svc_user = f"nr.acl.svc.{suffix}"
    pw = "acl-test-secret"
    victim = f"nr.reply.{suffix}victim"

    _mgmt("PUT", f"/api/users/{client_user}", {"password": pw, "tags": ""})
    _mgmt("PUT", f"/api/users/{svc_user}", {"password": pw, "tags": ""})
    _mgmt("PUT", f"/api/permissions/%2F/{client_user}", client_perms)
    _mgmt("PUT", f"/api/permissions/%2F/{svc_user}", svc_perms)

    host = os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1")
    port = _amqp_port()
    admin = AmqpConnection(
        ConnectionConfig(
            host=host,
            port=port,
            username=os.environ.get("NUROPB_RMQ_USER", "guest"),
            password=os.environ.get("NUROPB_RMQ_PASSWORD", "guest"),
        )
    )
    try:
        await admin.connect()
        ch = await admin.open_channel(1)
        await admin.queue_declare(ch, victim, exclusive=False, auto_delete=True)
    finally:
        await admin.close()

    forge = AmqpConnection(
        ConnectionConfig(host=host, port=port, username=client_user, password=pw)
    )
    try:
        await forge.connect()
        ch = await forge.open_channel(1)
        close_wait = asyncio.create_task(forge._expect(ch, m.CHANNEL, m.CHANNEL_CLOSE))
        await asyncio.sleep(0)
        try:
            await forge.basic_publish(ch, b"forge", routing_key=victim, mandatory=True)
        except ProtocolError:
            close_wait.cancel()
            try:
                await close_wait
            except (asyncio.CancelledError, Exception):
                pass
        else:
            try:
                closed = await asyncio.wait_for(close_wait, timeout=5)
            except TimeoutError:
                pytest.fail(
                    "expected channel.close 403 ACCESS_REFUSED on default-exchange forge"
                )
            assert int(closed.args.get("reply_code", 0)) == 403
            text = str(closed.args.get("reply_text", "")).lower()
            assert "amq.default" in text or "refused" in text
    finally:
        try:
            await forge.close()
        except Exception:
            pass

    svc = AmqpConnection(
        ConnectionConfig(host=host, port=port, username=svc_user, password=pw)
    )
    try:
        await svc.connect()
        ch = await svc.open_channel(1)
        await svc.basic_publish(ch, b"ok", routing_key=victim, mandatory=True, confirm=True)
    finally:
        await svc.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reply_publish_restricted_forge_denied_service_allowed() -> None:
    await _forge_denied_service_allowed(
        {"configure": r"^nr\.reply\.", "write": r"^nr\.mesh", "read": r"^nr\.reply\."},
        {
            "configure": r"^nr\.reply\.",
            "write": r"^nr\.mesh.*|^nr\.reply\..*|^nr\.dlx\..*|^amq\.default$",
            "read": r"^nr\.reply\.",
        },
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reply_acl_regex_narrower_than_prefix() -> None:
    """Broker perms are real regex, narrower than `nr.reply.` prefix, still 403."""
    hex8 = r"^nr\.reply\.[0-9a-f]{8}"
    await _forge_denied_service_allowed(
        {"configure": hex8, "write": r"^nr\.mesh$", "read": hex8},
        {
            "configure": hex8,
            "write": rf"{hex8}|^nr\.mesh$|^amq\.default$",
            "read": hex8,
        },
    )
