# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Unit tests for AMQP heartbeat send + missed-peer timeout."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from nuropb_rmq.protocol.connection_sm import ConnectionLost
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig
from nuropb_rmq.transport.frame import FrameType


@pytest.mark.asyncio
async def test_heartbeat_timeout_notifies_loss(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = AmqpConnection(ConnectionConfig(heartbeat=1))
    conn.sm.on_tcp_connected(tls=False)
    conn.sm.allow_amqp_header()
    # Pretend we are open enough to send frames.
    conn._writer = MagicMock()
    conn._writer.write = MagicMock()
    conn._writer.drain = AsyncMock()
    conn._writer.close = MagicMock()

    clock = {"t": 100.0}

    def fake_monotonic() -> float:
        return clock["t"]

    monkeypatch.setattr("nuropb_rmq.transport.connection.time.monotonic", fake_monotonic)

    sleeps: list[float] = []

    async def fake_sleep(dt: float) -> None:
        sleeps.append(dt)
        clock["t"] += dt
        if len(sleeps) >= 3:
            # Enough silence accrued after start at t=100 with interval 1 → 2× = 2.
            pass

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    conn._heartbeat_sec = 1
    conn._last_peer_frame_at = clock["t"]
    conn._heartbeat_task = asyncio.create_task(conn._heartbeat_loop())
    await asyncio.wait_for(conn._heartbeat_task, timeout=2)
    assert isinstance(conn._lost_exc, ConnectionLost)
    assert "heartbeat timeout" in str(conn._lost_exc)


@pytest.mark.asyncio
async def test_heartbeat_send_while_peer_active(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = AmqpConnection(ConnectionConfig(heartbeat=2))
    conn._writer = MagicMock()
    conn._writer.write = MagicMock()
    conn._writer.drain = AsyncMock()

    clock = {"t": 0.0}
    monkeypatch.setattr(
        "nuropb_rmq.transport.connection.time.monotonic", lambda: clock["t"]
    )

    sends = {"n": 0}
    original_send = conn._send_frame

    async def counting_send(frame):  # noqa: ANN001
        sends["n"] += 1
        assert frame.frame_type == FrameType.HEARTBEAT
        # Peer stays fresh.
        conn._note_peer_frame()
        if sends["n"] >= 2:
            conn._closed = True
        await original_send(frame)

    monkeypatch.setattr(conn, "_send_frame", counting_send)

    async def fake_sleep(dt: float) -> None:
        clock["t"] += dt

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    conn._heartbeat_sec = 2
    conn._last_peer_frame_at = 0.0
    await conn._heartbeat_loop()
    assert sends["n"] >= 2
    assert conn._lost_exc is None


@pytest.mark.asyncio
async def test_stop_heartbeat_cancels_task() -> None:
    conn = AmqpConnection()
    conn._heartbeat_task = asyncio.create_task(asyncio.sleep(60))
    conn._stop_heartbeat()
    assert conn._heartbeat_task is None
    # Allow cancelled task to settle.
    await asyncio.sleep(0)
