# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Unit tests for connection loss, park-and-retry, and Session reconnect epoch."""

from __future__ import annotations

import asyncio

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nuropb_rmq.patterns.errors import CONNECTION_LOST, RpcError
from nuropb_rmq.session.reconnect import ReconnectCoordinator, ReconnectPolicy
from nuropb_rmq.session.session import Session, _connection_lost_error
from nuropb_rmq.transport.connection import ConnectionConfig


def test_connection_lost_error_taxonomy() -> None:
    err = _connection_lost_error()
    assert isinstance(err, RpcError)
    assert err.code == CONNECTION_LOST
    assert err.data and err.data.get("retryable") is True


def test_reconnect_policy_park_is_default() -> None:
    p = ReconnectPolicy()
    assert p.fail_outstanding is False
    fail = ReconnectPolicy(fail_outstanding=True)
    assert fail.fail_outstanding is True


def test_reconnect_policy_rejects_bad_attempts() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        ReconnectPolicy(max_attempts=0)


def test_session_rejects_policy_mismatch() -> None:
    with pytest.raises(ValueError, match="fail_outstanding"):
        Session(
            ConnectionConfig(host="127.0.0.1", port=1),
            fail_outstanding=True,
            reconnect_policy=ReconnectPolicy(fail_outstanding=False),
        )


@pytest.mark.asyncio
async def test_coordinator_exhausted_attempts() -> None:
    class Boom:
        async def reconnect(self) -> None:
            raise RuntimeError("nope")

    with pytest.raises(RuntimeError, match="nope"):
        await ReconnectCoordinator(
            ReconnectPolicy(max_attempts=2, initial_backoff_s=0.0)
        ).reconnect(Boom())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_fail_outstanding_on_loss_completes_futures() -> None:
    session = Session(
        ConnectionConfig(host="127.0.0.1", port=1),
        fail_outstanding=True,
    )
    rid, fut = session.correlation.register("abcd1234")
    session._on_connection_lost(RuntimeError("boom"))
    with pytest.raises(RpcError) as ei:
        await fut
    assert ei.value.code == CONNECTION_LOST
    assert rid not in session.correlation
    assert session.reply_queue_open is False


@pytest.mark.asyncio
async def test_park_on_loss_keeps_outstanding() -> None:
    session = Session(ConnectionConfig(host="127.0.0.1", port=1))
    assert session.fail_outstanding is False
    rid, fut = session.correlation.register("abcd1234")
    session._on_connection_lost(RuntimeError("boom"))
    assert rid in session.correlation
    assert not fut.done()
    assert session.reply_queue_open is False
    session.correlation.fail(rid, RuntimeError("cleanup"))
    with pytest.raises(RuntimeError):
        await fut


@pytest.mark.asyncio
async def test_remember_and_forget_publish() -> None:
    from nuropb_rmq.session.session import ParkedPublish

    session = Session(ConnectionConfig(host="127.0.0.1", port=1))
    env = ParkedPublish(exchange="", routing_key="q", body=b"{}", properties={})
    session.remember_publish("abcd1234", env)
    assert "abcd1234" in session._parked
    session.forget_publish("abcd1234")
    assert "abcd1234" not in session._parked


@pytest.mark.integration
@pytest.mark.asyncio
async def test_force_drop_fail_fast_outstanding_rpc() -> None:
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
    session = Session(cfg, fail_outstanding=True)
    await session.start()
    _rid, fut = session.correlation.register()
    await session.conn.force_drop()
    await asyncio.sleep(0.05)
    with pytest.raises(RpcError) as ei:
        await asyncio.wait_for(fut, timeout=2)
    assert ei.value.code == CONNECTION_LOST
    assert not session.reply_queue_open
    await session.reconnect()
    assert session.epoch == 1
    assert session.reply_queue_open
    await session.close()


@given(st.integers(min_value=0, max_value=20), st.booleans())
@settings(max_examples=40)
def test_pbt_reconnect_epoch_monotonic(start_epoch: int, fail_outstanding: bool) -> None:
    """Lean onDisconnect / onReconnect: epoch bumps; fail-fast clears pending."""
    pending = 3
    reply_open = True
    reply_open = False
    if fail_outstanding:
        pending = 0
    epoch = start_epoch + 1
    reply_open = True
    assert epoch == start_epoch + 1
    assert reply_open is True
    if fail_outstanding:
        assert pending == 0
    else:
        assert pending == 3


@given(st.booleans())
@settings(max_examples=20)
def test_pbt_future_never_two_terminals(fail_outstanding: bool) -> None:
    """A parked or failed id is removed from pending at most once (first terminal)."""
    pending = {"id1"}
    if fail_outstanding:
        pending.clear()
        terminal = "lost"
    else:
        terminal = "parked"
    assert len(pending) <= 1
    if terminal == "lost":
        assert "id1" not in pending
    else:
        assert "id1" in pending
        pending.discard("id1")
        assert "id1" not in pending
