"""Property-based tests mirroring Lean Protocol SM invariants 1, 2, 4, 7."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nuropb_rmq.protocol import methods as m
from nuropb_rmq.protocol.connection_sm import ConnectionStateMachine, ConnState, ProtocolError


def _fresh() -> ConnectionStateMachine:
    return ConnectionStateMachine()


@given(st.integers(min_value=1, max_value=60))
@settings(max_examples=40)
def test_inv7_valid_heartbeat_accepted(hb: int) -> None:
    sm = _fresh()
    sm.on_tcp_connected(tls=False)
    sm.allow_amqp_header()
    sm.on_connection_start()
    sm.on_connection_start_ok_sent()
    sm.on_connection_tune()
    sm.on_connection_tune_ok_sent(heartbeat=hb)
    assert sm.heartbeat == hb
    assert sm.state == ConnState.TUNE_OK


@given(st.one_of(st.just(0), st.integers(min_value=61, max_value=10_000)))
@settings(max_examples=40)
def test_inv7_invalid_heartbeat_tears_down(hb: int) -> None:
    sm = _fresh()
    sm.on_tcp_connected(tls=False)
    sm.allow_amqp_header()
    sm.on_connection_start()
    sm.on_connection_start_ok_sent()
    sm.on_connection_tune()
    with pytest.raises(ProtocolError):
        sm.on_connection_tune_ok_sent(heartbeat=hb)
    assert sm.state == ConnState.ERROR


@given(st.sampled_from([m.CONNECTION_START_OK, m.CONNECTION_TUNE_OK, m.CONNECTION_OPEN]))
@settings(max_examples=30)
def test_inv1_illegal_send_from_init_tears_down(method_id: int) -> None:
    sm = _fresh()
    with pytest.raises(ProtocolError):
        sm.assert_can_send_connection_method(method_id)
    assert sm.state == ConnState.ERROR


@given(st.booleans())
@settings(max_examples=20)
def test_inv2_amqp_before_tls_verify_fails(use_tls: bool) -> None:
    sm = _fresh()
    sm.on_tcp_connected(tls=use_tls)
    if use_tls:
        with pytest.raises(ProtocolError, match="before TLS"):
            sm.allow_amqp_header()
        assert sm.state == ConnState.ERROR
    else:
        sm.allow_amqp_header()
        assert sm.state == ConnState.TCP_CONNECTED


@given(st.lists(st.sampled_from(["open_ok", "tune", "start_ok"]), min_size=1, max_size=6))
@settings(max_examples=50)
def test_inv4_out_of_order_events_fail_closed(events: list[str]) -> None:
    """Illegal transitions from INIT must land in ERROR (Lean reject_implies_error)."""
    sm = _fresh()
    raised = False
    for ev in events:
        try:
            if ev == "open_ok":
                sm.on_connection_open_ok()
            elif ev == "tune":
                sm.on_connection_tune()
            elif ev == "start_ok":
                sm.on_connection_start_ok_sent()
        except ProtocolError:
            raised = True
            break
    assert raised
    assert sm.state == ConnState.ERROR


def test_inv4_reject_path_never_silent() -> None:
    sm = _fresh()
    sm.on_tcp_connected(tls=False)
    before = sm.state
    with pytest.raises(ProtocolError):
        sm.on_connection_open_ok()
    assert sm.state == ConnState.ERROR
    assert sm.state != before


def test_inv3_start_ok_after_verified_tls() -> None:
    """Lean startOk_requires_verified_tls: TLS path reaches START only after verify."""
    sm = _fresh()
    sm.on_tcp_connected(tls=True)
    sm.on_tls_verified()
    assert sm.state == ConnState.TLS_VERIFIED
    sm.allow_amqp_header()
    sm.on_connection_start()
    sm.assert_can_send_connection_method(m.CONNECTION_START_OK)
    sm.on_connection_start_ok_sent()
    assert sm.state == ConnState.START_OK


def test_inv5_begin_close_from_open_ok() -> None:
    """Lean beginClose_ok_from_openOk / close_reachable_all."""
    sm = _fresh()
    sm.on_tcp_connected(tls=False)
    sm.allow_amqp_header()
    sm.on_connection_start()
    sm.on_connection_start_ok_sent()
    sm.on_connection_tune()
    sm.on_connection_tune_ok_sent(heartbeat=30)
    sm.on_connection_open_sent()
    sm.on_connection_open_ok()
    sm.begin_close()
    assert sm.state == ConnState.CLOSING
    sm.assert_can_send_connection_method(m.CONNECTION_CLOSE_OK)
    sm.on_close_ok()
    assert sm.state == ConnState.CLOSED


def test_inv5_begin_close_rejected_from_error() -> None:
    sm = _fresh()
    with pytest.raises(ProtocolError):
        sm.on_connection_open_ok()
    assert sm.state == ConnState.ERROR
    with pytest.raises(ProtocolError):
        sm.begin_close()
    assert sm.state == ConnState.ERROR


@pytest.mark.asyncio
async def test_inv7_connect_rejects_heartbeat_out_of_range() -> None:
    from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig

    conn = AmqpConnection(ConnectionConfig(heartbeat=90))
    with pytest.raises(ValueError, match="1..60"):
        await conn.connect()
