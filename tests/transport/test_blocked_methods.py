# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Unit tests for connection.blocked handling and confirm method codecs."""

from __future__ import annotations

import pytest

from nuropb_rmq.api import ConnectionBlockedError
from nuropb_rmq.protocol import methods as m
from nuropb_rmq.protocol.channel_sm import ChannelStateMachine
from nuropb_rmq.protocol.methods import Method, decode_method, encode_method
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig


def test_encode_decode_confirm_select() -> None:
    raw = encode_method(Method(m.CONFIRM, m.CONFIRM_SELECT, {"nowait": False}))
    # decode of select-ok
    ok = decode_method(
        m.CONFIRM.to_bytes(2, "big") + m.CONFIRM_SELECT_OK.to_bytes(2, "big")
    )
    assert ok.class_id == m.CONFIRM
    assert ok.method_id == m.CONFIRM_SELECT_OK
    assert len(raw) >= 4


def test_decode_blocked_unblocked() -> None:
    from nuropb_rmq.transport.frame import encode_shortstr

    reason = encode_shortstr("low_memory")
    payload = (
        m.CONNECTION.to_bytes(2, "big")
        + m.CONNECTION_BLOCKED.to_bytes(2, "big")
        + reason
    )
    method = decode_method(payload)
    assert method.method_id == m.CONNECTION_BLOCKED
    assert method.args["reason"] == "low_memory"

    ub = decode_method(
        m.CONNECTION.to_bytes(2, "big") + m.CONNECTION_UNBLOCKED.to_bytes(2, "big")
    )
    assert ub.method_id == m.CONNECTION_UNBLOCKED


def test_encode_nack_reject_cancel() -> None:
    encode_method(
        Method(m.BASIC, m.BASIC_NACK, {"delivery_tag": 3, "multiple": False, "requeue": False})
    )
    encode_method(Method(m.BASIC, m.BASIC_REJECT, {"delivery_tag": 3, "requeue": True}))
    encode_method(Method(m.BASIC, m.BASIC_CANCEL, {"consumer_tag": "ctag", "nowait": False}))


def test_connection_starts_unblocked() -> None:
    conn = AmqpConnection(ConnectionConfig())
    assert conn._publish_blocked is False


@pytest.mark.asyncio
async def test_publish_raises_connection_blocked_error() -> None:
    conn = AmqpConnection(ConnectionConfig())
    ch = ChannelStateMachine(1)
    ch.on_open_sent()
    ch.on_open_ok()
    conn._channels[1] = ch
    conn._publish_blocked = True
    with pytest.raises(ConnectionBlockedError, match="connection.blocked"):
        await conn.basic_publish(1, b"x", confirm=False)
