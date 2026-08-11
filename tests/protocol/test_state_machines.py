"""Unit tests for connection/channel state machines (fail-closed)."""

from __future__ import annotations

import pytest

from nuropb_rmq.protocol.channel_sm import ChannelStateMachine, ChanState
from nuropb_rmq.protocol.connection_sm import ConnState, ConnectionStateMachine, ProtocolError
from nuropb_rmq.protocol import methods as m


def test_happy_path_plain() -> None:
    sm = ConnectionStateMachine()
    sm.on_tcp_connected(tls=False)
    sm.allow_amqp_header()
    sm.on_connection_start()
    sm.on_connection_start_ok_sent()
    sm.on_connection_tune()
    sm.on_connection_tune_ok_sent(heartbeat=30)
    assert sm.heartbeat == 30
    sm.on_connection_open_sent()
    sm.on_connection_open_ok()
    assert sm.is_open


def test_tls_required_before_amqp() -> None:
    sm = ConnectionStateMachine()
    sm.on_tcp_connected(tls=True)
    assert sm.state == ConnState.TLS_HANDSHAKING
    with pytest.raises(ProtocolError, match="before TLS"):
        sm.allow_amqp_header()
    assert sm.state == ConnState.ERROR


def test_rejected_transition_tears_down() -> None:
    sm = ConnectionStateMachine()
    sm.on_tcp_connected(tls=False)
    with pytest.raises(ProtocolError):
        sm.on_connection_open_ok()
    assert sm.state == ConnState.ERROR


def test_illegal_method_send_rejected() -> None:
    sm = ConnectionStateMachine()
    sm.on_tcp_connected(tls=False)
    with pytest.raises(ProtocolError):
        sm.assert_can_send_connection_method(m.CONNECTION_OPEN)
    assert sm.state == ConnState.ERROR


def test_channel_ops_require_open() -> None:
    ch = ChannelStateMachine(1)
    with pytest.raises(ProtocolError):
        ch.assert_open_for_ops()
    assert ch.state == ChanState.ERROR


def test_channel_open_path() -> None:
    ch = ChannelStateMachine(1)
    ch.on_open_sent()
    ch.on_open_ok()
    ch.assert_open_for_ops()
