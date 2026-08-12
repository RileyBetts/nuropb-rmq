"""Unit tests for AMQP frame codec bounds checking."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nuropb_rmq.transport.frame import (
    DEFAULT_FRAME_MAX,
    DEFAULT_MAX_TABLE_DEPTH,
    AmqpCodecError,
    Frame,
    FrameType,
    decode_frame,
    decode_table,
    encode_frame,
    encode_table,
)


def test_roundtrip_method_frame() -> None:
    payload = b"\x00\x0a\x00\x0a" + b"rest"
    raw = encode_frame(Frame(FrameType.METHOD, 1, payload))
    frame, nxt = decode_frame(raw)
    assert frame.frame_type == FrameType.METHOD
    assert frame.channel == 1
    assert frame.payload == payload
    assert nxt == len(raw)


def test_rejects_oversize_length_before_accept() -> None:
    # Craft header claiming huge size without providing payload
    header = bytes([FrameType.METHOD]) + (0).to_bytes(2, "big") + (10_000_000).to_bytes(4, "big")
    with pytest.raises(AmqpCodecError, match="exceeds max payload"):
        decode_frame(header + b"x" * 100, frame_max=131072)


def test_encode_rejects_payload_at_old_broken_limit() -> None:
    """Payload == frame_max must fail (wire size would be frame_max+8)."""
    from nuropb_rmq.transport.frame import FRAME_OVERHEAD, max_frame_payload

    payload_max = max_frame_payload(DEFAULT_FRAME_MAX)
    assert payload_max == DEFAULT_FRAME_MAX - FRAME_OVERHEAD
    ok = encode_frame(Frame(FrameType.BODY, 1, b"x" * payload_max))
    assert len(ok) == DEFAULT_FRAME_MAX
    with pytest.raises(AmqpCodecError, match="exceeds max payload"):
        encode_frame(Frame(FrameType.BODY, 1, b"x" * (payload_max + 1)))


def test_table_roundtrip_float_array_decimal() -> None:
    from datetime import UTC, datetime
    from decimal import Decimal

    table = {
        "rate": 1.5,
        "tags": ["a", "b"],
        "when": datetime(2024, 1, 1, tzinfo=UTC),
        "amt": Decimal("12.34"),
    }
    encoded = encode_table(table)
    decoded, end = decode_table(encoded)
    assert end == len(encoded)
    assert decoded["rate"] == pytest.approx(1.5)
    assert decoded["tags"] == ["a", "b"]
    assert decoded["when"] == int(datetime(2024, 1, 1, tzinfo=UTC).timestamp())
    assert decoded["amt"] == (2, 1234)


def test_rejects_deep_table_nesting() -> None:
    # Build nested tables deeper than max
    table: dict = {"a": {}}
    cur = table["a"]
    for i in range(DEFAULT_MAX_TABLE_DEPTH + 5):
        cur["n"] = {}
        cur = cur["n"]
    with pytest.raises(AmqpCodecError, match="nesting exceeds"):
        encode_table(table, max_depth=DEFAULT_MAX_TABLE_DEPTH)


def test_table_roundtrip_shallow() -> None:
    table = {"product": "nuropb-rmq", "capabilities": {"foo": True}}
    encoded = encode_table(table)
    decoded, end = decode_table(encoded)
    assert end == len(encoded)
    assert decoded["product"] == "nuropb-rmq"
    assert decoded["capabilities"]["foo"] is True


def test_decodes_timestamp_and_array_for_x_death() -> None:
    """Dead-lettered messages carry x-death arrays with timestamp 'T' fields."""
    from nuropb_rmq.transport.frame import decode_field_value, encode_shortstr, encode_table

    # Array of one table: {count: long, time: timestamp}
    # Build table body without outer length, then wrap as field-value 'F'+table
    table_payload = encode_table({"count": 1})  # uses 'I' for int — fine
    # Manually append timestamp field into a custom table
    parts = bytearray()
    parts += encode_shortstr("count")
    parts += b"l" + (1).to_bytes(8, "big")
    parts += encode_shortstr("time")
    parts += b"T" + (1_700_000_000).to_bytes(8, "big")
    table = len(parts).to_bytes(4, "big") + bytes(parts)
    inner = b"F" + table
    array = b"A" + len(inner).to_bytes(4, "big") + inner
    val, end = decode_field_value(array, 0)
    assert end == len(array)
    assert isinstance(val, list) and len(val) == 1
    assert val[0]["count"] == 1
    assert val[0]["time"] == 1_700_000_000
    _ = table_payload


def test_heartbeat_frame() -> None:
    raw = encode_frame(Frame(FrameType.HEARTBEAT, 0, b""))
    frame, _ = decode_frame(raw)
    assert frame.frame_type == FrameType.HEARTBEAT
    assert frame.payload == b""


@given(st.integers(min_value=DEFAULT_FRAME_MAX - 7, max_value=DEFAULT_FRAME_MAX * 4))
@settings(max_examples=30)
def test_inv6_pbt_oversize_length_rejected(claimed_size: int) -> None:
    """Lean `decodeAccepted_reject_oversize` / inv6 (payload > frame_max-8)."""
    header = (
        bytes([FrameType.METHOD])
        + (0).to_bytes(2, "big")
        + claimed_size.to_bytes(4, "big")
    )
    with pytest.raises(AmqpCodecError, match="exceeds max payload"):
        decode_frame(header, frame_max=DEFAULT_FRAME_MAX)


@given(st.integers(min_value=DEFAULT_MAX_TABLE_DEPTH + 1, max_value=DEFAULT_MAX_TABLE_DEPTH + 20))
@settings(max_examples=20)
def test_inv6_pbt_deep_nesting_rejected(depth: int) -> None:
    table: dict = {}
    cur = table
    for _ in range(depth):
        cur["n"] = {}
        cur = cur["n"]
    with pytest.raises(AmqpCodecError, match="nesting exceeds"):
        encode_table(table, max_depth=DEFAULT_MAX_TABLE_DEPTH)
