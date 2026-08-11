"""Dedicated frame-decode fuzz lane (malformed / adversarial inputs).

Decode must return a frame or raise ``AmqpCodecError`` — never hang or
allocate unbounded buffers past ``frame_max`` / table-depth ceilings.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nuropb_rmq.transport.frame import (
    DEFAULT_FRAME_MAX,
    DEFAULT_MAX_TABLE_DEPTH,
    AmqpCodecError,
    FrameType,
    decode_field_value,
    decode_frame,
    decode_table,
    encode_table,
)

pytestmark = pytest.mark.fuzz


def _try_decode_frame(data: bytes) -> None:
    try:
        decode_frame(data, frame_max=DEFAULT_FRAME_MAX)
    except AmqpCodecError:
        return


def _try_decode_table(data: bytes) -> None:
    try:
        decode_table(data, max_depth=DEFAULT_MAX_TABLE_DEPTH)
    except AmqpCodecError:
        return


def _try_decode_field(data: bytes) -> None:
    try:
        decode_field_value(data, 0, max_depth=DEFAULT_MAX_TABLE_DEPTH)
    except AmqpCodecError:
        return


@given(st.binary(min_size=0, max_size=4096))
@settings(max_examples=80, deadline=None)
def test_fuzz_decode_frame_random_bytes(data: bytes) -> None:
    _try_decode_frame(data)


@given(
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=0xFFFF),
    st.integers(min_value=0, max_value=DEFAULT_FRAME_MAX * 4),
    st.binary(min_size=0, max_size=256),
)
@settings(max_examples=100, deadline=None)
def test_fuzz_decode_frame_adversarial_header(
    frame_type: int, channel: int, size: int, tail: bytes
) -> None:
    header = bytes([frame_type]) + channel.to_bytes(2, "big") + size.to_bytes(4, "big")
    _try_decode_frame(header + tail)


@given(st.binary(min_size=0, max_size=2048))
@settings(max_examples=60, deadline=None)
def test_fuzz_decode_table_random_bytes(data: bytes) -> None:
    _try_decode_table(data)


@given(st.binary(min_size=0, max_size=1024))
@settings(max_examples=60, deadline=None)
def test_fuzz_decode_field_value_random_bytes(data: bytes) -> None:
    _try_decode_field(data)


@given(st.integers(min_value=DEFAULT_MAX_TABLE_DEPTH + 1, max_value=DEFAULT_MAX_TABLE_DEPTH + 40))
@settings(max_examples=25, deadline=None)
def test_fuzz_encode_table_deep_nesting_rejected(depth: int) -> None:
    table: dict = {}
    cur = table
    for _ in range(depth):
        cur["n"] = {}
        cur = cur["n"]
    with pytest.raises(AmqpCodecError, match="nesting exceeds"):
        encode_table(table, max_depth=DEFAULT_MAX_TABLE_DEPTH)


@given(st.sampled_from(list(FrameType)), st.integers(min_value=0, max_value=7))
@settings(max_examples=40, deadline=None)
def test_fuzz_truncated_well_typed_header(frame_type: FrameType, trunc: int) -> None:
    # Valid-looking type/channel with truncated size/payload.
    header = bytes([int(frame_type)]) + (1).to_bytes(2, "big") + (32).to_bytes(4, "big")
    blob = header[: max(0, len(header) - trunc)]
    _try_decode_frame(blob)
