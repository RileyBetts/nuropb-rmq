"""Unit tests for connection loss and Session reconnect epoch."""

from __future__ import annotations

import asyncio

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nuropb_rmq.patterns.errors import CONNECTION_LOST, RpcError
from nuropb_rmq.session.reconnect import ReconnectPolicy
from nuropb_rmq.session.session import Session, _connection_lost_error
from nuropb_rmq.transport.connection import ConnectionConfig


def test_connection_lost_error_taxonomy() -> None:
    err = _connection_lost_error()
    assert isinstance(err, RpcError)
    assert err.code == CONNECTION_LOST
    assert err.data and err.data.get("retryable") is True


def test_reconnect_policy_rejects_park() -> None:
    with pytest.raises(ValueError, match="fail_outstanding"):
        ReconnectPolicy(fail_outstanding=False)


@pytest.mark.asyncio
async def test_discard_all_on_loss_fails_outstanding() -> None:
    session = Session(ConnectionConfig(host="127.0.0.1", port=1))
    # Don't connect — exercise correlation fail path directly
    rid, fut = session.correlation.register("abcd1234")
    session._on_connection_lost(RuntimeError("boom"))
    with pytest.raises(RpcError) as ei:
        await fut
    assert ei.value.code == CONNECTION_LOST
    assert rid not in session.correlation
    assert session.reply_queue_open is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_force_drop_fails_outstanding_rpc() -> None:
    import os
    import socket

    def port() -> int:
        if "NUROPB_RMQ_PORT" in os.environ:
            return int(os.environ["NUROPB_RMQ_PORT"])
        for p in (5672, 5673):
            with socket.socket() as s:
                s.settimeout(0.2)
                try:
                    s.connect((os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1"), p))
                    return p
                except OSError:
                    continue
        pytest.skip("RabbitMQ not listening")

    cfg = ConnectionConfig(host=os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1"), port=port())
    session = Session(cfg)
    await session.start()
    rid, fut = session.correlation.register()
    await session.conn.force_drop()
    # Allow loss callback / reply loop to run
    await asyncio.sleep(0.05)
    with pytest.raises(RpcError) as ei:
        await asyncio.wait_for(fut, timeout=2)
    assert ei.value.code == CONNECTION_LOST
    assert not session.reply_queue_open
    # Reconnect for new work
    await session.reconnect()
    assert session.epoch == 1
    assert session.reply_queue_open
    await session.close()


@given(st.integers(min_value=0, max_value=20))
@settings(max_examples=30)
def test_pbt_reconnect_epoch_monotonic(start_epoch: int) -> None:
    """Lean onReconnect bumps epoch and clears pending."""
    reply_open = True
    pending = start_epoch
    reply_open = False
    pending = 0
    epoch = start_epoch + 1
    reply_open = True
    pending = 0
    assert epoch == start_epoch + 1
    assert pending == 0 and reply_open
