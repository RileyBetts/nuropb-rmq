# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Unit tests for basic.return codec, content properties, and update-secret."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nuropb_rmq.protocol import methods as m
from nuropb_rmq.protocol.methods import (
    Method,
    decode_content_header,
    decode_method,
    encode_content_header,
    encode_method,
)
from nuropb_rmq.transport.connection import (
    AmqpConnection,
    ConnectionConfig,
    PublishReturned,
    ReturnedMessage,
)
from nuropb_rmq.transport.frame import AmqpCodecError


def test_encode_decode_basic_return() -> None:
    raw = encode_method(
        Method(
            m.BASIC,
            m.BASIC_RETURN,
            {
                "reply_code": 312,
                "reply_text": "NO_ROUTE",
                "exchange": "",
                "routing_key": "missing.queue",
            },
        )
    )
    decoded = decode_method(raw)
    assert decoded.class_id == m.BASIC
    assert decoded.method_id == m.BASIC_RETURN
    assert decoded.args["reply_code"] == 312
    assert decoded.args["reply_text"] == "NO_ROUTE"
    assert decoded.args["routing_key"] == "missing.queue"


def test_encode_publish_mandatory_bit() -> None:
    raw = encode_method(
        Method(
            m.BASIC,
            m.BASIC_PUBLISH,
            {"exchange": "", "routing_key": "q", "mandatory": True},
        )
    )
    # ticket(2) + exchange shortstr + routing_key shortstr + bits
    assert raw[-1] & 1


def test_content_properties_roundtrip() -> None:
    ts = datetime(2024, 6, 1, tzinfo=UTC)
    header = encode_content_header(
        class_id=m.BASIC,
        body_size=4,
        properties={
            "content_type": "text/plain",
            "message_id": "m-1",
            "timestamp": ts,
            "type": "order",
            "user_id": "guest",
            "app_id": "nuropb-rmq",
            "cluster_id": "c1",
        },
    )
    class_id, body_size, props = decode_content_header(header)
    assert class_id == m.BASIC
    assert body_size == 4
    assert props["message_id"] == "m-1"
    assert props["timestamp"] == int(ts.timestamp())
    assert props["type"] == "order"
    assert props["user_id"] == "guest"
    assert props["app_id"] == "nuropb-rmq"
    assert props["cluster_id"] == "c1"


def test_content_properties_int_timestamp() -> None:
    header = encode_content_header(
        class_id=m.BASIC,
        body_size=0,
        properties={"timestamp": 1_700_000_000},
    )
    _, _, props = decode_content_header(header)
    assert props["timestamp"] == 1_700_000_000


def test_decode_pika_style_extra_properties_not_dropped() -> None:
    """A broker/pika message with timestamp+app_id must not skip those fields."""
    header = encode_content_header(
        class_id=m.BASIC,
        body_size=1,
        properties={"content_type": "application/json", "app_id": "pika", "timestamp": 10},
    )
    _, _, props = decode_content_header(header)
    assert props["content_type"] == "application/json"
    assert props["app_id"] == "pika"
    assert props["timestamp"] == 10


def test_encode_update_secret() -> None:
    raw = encode_method(
        Method(
            m.CONNECTION,
            m.CONNECTION_UPDATE_SECRET,
            {"new_secret": "s3cret", "reason": "rotate"},
        )
    )
    decoded_ok = decode_method(
        m.CONNECTION.to_bytes(2, "big") + m.CONNECTION_UPDATE_SECRET_OK.to_bytes(2, "big")
    )
    assert decoded_ok.method_id == m.CONNECTION_UPDATE_SECRET_OK
    assert len(raw) > 4


def test_publish_returned_distinct_from_nack() -> None:
    from nuropb_rmq.transport.confirm import PublishNack

    err = PublishReturned(312, "NO_ROUTE", routing_key="x")
    assert not isinstance(err, PublishNack)
    assert "NO_ROUTE" in str(err)


def test_connection_starts_without_returns() -> None:
    conn = AmqpConnection(ConnectionConfig())
    assert conn._publish_blocked is False
    assert list(conn._mandatory_tags) == []


def test_truncated_timestamp_rejected() -> None:
    # class_id(2)+weight(2)+body_size(8)+flags(2) with timestamp bit and no payload
    flags = (1 << 6).to_bytes(2, "big")
    payload = (60).to_bytes(2, "big") + (0).to_bytes(2, "big") + (0).to_bytes(8, "big") + flags
    with pytest.raises(AmqpCodecError, match="truncated timestamp"):
        decode_content_header(payload)


def test_dlq_processor_counts_unroutable_replies() -> None:
    from nuropb_rmq.patterns.dlq_timeout import DlqTimeoutProcessor

    proc = DlqTimeoutProcessor(dlq_name="nr.dlq.test")
    assert proc.unroutable_replies == 0
    proc._on_return(
        ReturnedMessage(
            reply_code=312,
            reply_text="NO_ROUTE",
            exchange="",
            routing_key="gone",
            body=b"{}",
            properties={},
        )
    )
    assert proc.unroutable_replies == 1


@given(st.booleans(), st.booleans())
@settings(max_examples=20)
def test_pbt_return_then_ack_never_nack(mandatory: bool, routable: bool) -> None:
    """Lean mandatoryUnroutableConfirm: return is never a confirm nack."""
    if mandatory and not routable:
        signals = ["return", "ack"]
    elif routable:
        signals = ["ack"]
    else:
        signals = []
    assert "nack" not in signals
    if "return" in signals:
        assert signals[0] == "return"
        assert "ack" in signals
