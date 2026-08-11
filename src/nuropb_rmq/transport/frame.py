"""AMQP 0-9-1 frame encode/decode with bounds checks (SpeC++ invariant 6)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

FRAME_END = 0xCE
DEFAULT_FRAME_MAX = 131072
DEFAULT_MAX_TABLE_DEPTH = 32


class FrameType(IntEnum):
    METHOD = 1
    HEADER = 2
    BODY = 3
    HEARTBEAT = 8


class AmqpCodecError(ValueError):
    """Malformed or oversize AMQP frame/field data."""


@dataclass(frozen=True, slots=True)
class Frame:
    frame_type: FrameType
    channel: int
    payload: bytes


def encode_frame(frame: Frame, *, frame_max: int = DEFAULT_FRAME_MAX) -> bytearray:
    if frame.channel < 0 or frame.channel > 0xFFFF:
        raise AmqpCodecError(f"channel out of range: {frame.channel}")
    size = len(frame.payload)
    if size > frame_max:
        raise AmqpCodecError(f"frame payload {size} exceeds frame_max {frame_max}")
    buf = bytearray(8 + size)
    struct.pack_into("!BHI", buf, 0, int(frame.frame_type), frame.channel, size)
    buf[7 : 7 + size] = frame.payload
    buf[-1] = FRAME_END
    return buf


def decode_frame(
    data: bytes | bytearray | memoryview,
    *,
    frame_max: int = DEFAULT_FRAME_MAX,
    offset: int = 0,
) -> tuple[Frame, int]:
    """Decode one frame from ``data[offset:]``.

    Validates the length prefix against ``frame_max`` *before* accepting the
    payload (never allocates proportional to an unvalidated length).
    Accepts ``bytearray`` / ``memoryview`` so callers can decode without
    copying the entire receive buffer.
    """
    view = memoryview(data)
    if len(view) - offset < 7:
        raise AmqpCodecError("incomplete frame header")
    frame_type_i = view[offset]
    try:
        frame_type = FrameType(frame_type_i)
    except ValueError as exc:
        raise AmqpCodecError(f"unknown frame type {frame_type_i}") from exc
    channel = int.from_bytes(view[offset + 1 : offset + 3], "big")
    size = int.from_bytes(view[offset + 3 : offset + 7], "big")
    if size < 0 or size > frame_max:
        raise AmqpCodecError(f"frame size {size} exceeds frame_max {frame_max}")
    end = offset + 7 + size
    if len(view) < end + 1:
        raise AmqpCodecError("incomplete frame payload")
    if view[end] != FRAME_END:
        raise AmqpCodecError(f"bad frame end byte 0x{view[end]:02x}")
    payload = bytes(view[offset + 7 : end])
    return Frame(frame_type=frame_type, channel=channel, payload=payload), end + 1


# --- Wire primitives / field tables ---


def encode_shortstr(value: str) -> bytes:
    raw = value.encode("utf-8")
    if len(raw) > 255:
        raise AmqpCodecError("shortstr exceeds 255 octets")
    return bytes([len(raw)]) + raw


def decode_shortstr(data: bytes, offset: int = 0) -> tuple[str, int]:
    if offset >= len(data):
        raise AmqpCodecError("shortstr missing length")
    n = data[offset]
    start = offset + 1
    end = start + n
    if end > len(data):
        raise AmqpCodecError("shortstr truncated")
    return data[start:end].decode("utf-8"), end


def encode_longstr(value: bytes | str) -> bytes:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return len(raw).to_bytes(4, "big") + raw


def decode_longstr(data: bytes, offset: int = 0) -> tuple[bytes, int]:
    if offset + 4 > len(data):
        raise AmqpCodecError("longstr missing length")
    n = int.from_bytes(data[offset : offset + 4], "big")
    if n > DEFAULT_FRAME_MAX:
        raise AmqpCodecError(f"longstr length {n} exceeds ceiling")
    start = offset + 4
    end = start + n
    if end > len(data):
        raise AmqpCodecError("longstr truncated")
    return data[start:end], end


def encode_field_value(value: Any, *, depth: int = 0, max_depth: int = DEFAULT_MAX_TABLE_DEPTH) -> bytes:
    if depth > max_depth:
        raise AmqpCodecError(f"field-table nesting exceeds max_depth {max_depth}")
    if value is None:
        return b"V"
    if isinstance(value, bool):
        return b"t" + bytes([1 if value else 0])
    if isinstance(value, int):
        if -0x80000000 <= value <= 0x7FFFFFFF:
            return b"I" + value.to_bytes(4, "big", signed=True)
        return b"L" + value.to_bytes(8, "big", signed=True)
    if isinstance(value, str):
        return b"S" + encode_longstr(value)
    if isinstance(value, bytes):
        return b"x" + encode_longstr(value)
    if isinstance(value, dict):
        return b"F" + encode_table(value, depth=depth + 1, max_depth=max_depth)
    raise AmqpCodecError(f"unsupported field type {type(value)!r}")


def decode_field_value(
    data: bytes,
    offset: int = 0,
    *,
    depth: int = 0,
    max_depth: int = DEFAULT_MAX_TABLE_DEPTH,
) -> tuple[Any, int]:
    if depth > max_depth:
        raise AmqpCodecError(f"field-table nesting exceeds max_depth {max_depth}")
    if offset >= len(data):
        raise AmqpCodecError("missing field value type")
    tag = chr(data[offset])
    offset += 1

    def _need(n: int, what: str) -> None:
        if offset + n > len(data):
            raise AmqpCodecError(f"{what} truncated")

    if tag == "V":
        return None, offset
    if tag == "t":
        _need(1, "bool")
        return bool(data[offset]), offset + 1
    if tag == "b":
        _need(1, "byte")
        return int.from_bytes(data[offset : offset + 1], "big", signed=True), offset + 1
    if tag == "B":
        _need(1, "ubyte")
        return data[offset], offset + 1
    if tag == "U":
        _need(2, "ushort")
        return int.from_bytes(data[offset : offset + 2], "big"), offset + 2
    if tag == "u":
        _need(2, "short")
        return int.from_bytes(data[offset : offset + 2], "big", signed=True), offset + 2
    if tag == "i":
        _need(4, "uint")
        return int.from_bytes(data[offset : offset + 4], "big"), offset + 4
    if tag == "I":
        _need(4, "int")
        return int.from_bytes(data[offset : offset + 4], "big", signed=True), offset + 4
    if tag == "l":
        _need(8, "ulong")
        return int.from_bytes(data[offset : offset + 8], "big"), offset + 8
    if tag == "L":
        _need(8, "long")
        return int.from_bytes(data[offset : offset + 8], "big", signed=True), offset + 8
    if tag == "f":
        _need(4, "float")
        return struct.unpack(">f", data[offset : offset + 4])[0], offset + 4
    if tag == "d":
        _need(8, "double")
        return struct.unpack(">d", data[offset : offset + 8])[0], offset + 8
    if tag == "D":
        # decimal-value: scale (octet) + long-int
        _need(5, "decimal")
        scale = data[offset]
        value = int.from_bytes(data[offset + 1 : offset + 5], "big", signed=True)
        return (scale, value), offset + 5
    if tag == "T":
        # timestamp: 64-bit POSIX seconds
        _need(8, "timestamp")
        return int.from_bytes(data[offset : offset + 8], "big"), offset + 8
    if tag == "s":
        return decode_shortstr(data, offset)
    if tag == "S":
        raw, offset = decode_longstr(data, offset)
        return raw.decode("utf-8"), offset
    if tag == "x":
        return decode_longstr(data, offset)
    if tag == "F":
        return decode_table(data, offset, depth=depth + 1, max_depth=max_depth)
    if tag == "A":
        # array: skip with bounds
        if offset + 4 > len(data):
            raise AmqpCodecError("array missing length")
        n = int.from_bytes(data[offset : offset + 4], "big")
        if n > DEFAULT_FRAME_MAX:
            raise AmqpCodecError(f"array length {n} exceeds ceiling")
        end = offset + 4 + n
        if end > len(data):
            raise AmqpCodecError("array truncated")
        items: list[Any] = []
        pos = offset + 4
        while pos < end:
            item, pos = decode_field_value(data, pos, depth=depth + 1, max_depth=max_depth)
            items.append(item)
        return items, end
    raise AmqpCodecError(f"unsupported field tag {tag!r}")


def encode_table(
    table: dict[str, Any],
    *,
    depth: int = 0,
    max_depth: int = DEFAULT_MAX_TABLE_DEPTH,
) -> bytes:
    if depth > max_depth:
        raise AmqpCodecError(f"field-table nesting exceeds max_depth {max_depth}")
    parts = bytearray()
    for key, value in table.items():
        parts += encode_shortstr(key)
        parts += encode_field_value(value, depth=depth, max_depth=max_depth)
    return len(parts).to_bytes(4, "big") + bytes(parts)


def decode_table(
    data: bytes,
    offset: int = 0,
    *,
    depth: int = 0,
    max_depth: int = DEFAULT_MAX_TABLE_DEPTH,
) -> tuple[dict[str, Any], int]:
    if depth > max_depth:
        raise AmqpCodecError(f"field-table nesting exceeds max_depth {max_depth}")
    if offset + 4 > len(data):
        raise AmqpCodecError("table missing length")
    n = int.from_bytes(data[offset : offset + 4], "big")
    if n > DEFAULT_FRAME_MAX:
        raise AmqpCodecError(f"table length {n} exceeds ceiling")
    start = offset + 4
    end = start + n
    if end > len(data):
        raise AmqpCodecError("table truncated")
    result: dict[str, Any] = {}
    pos = start
    while pos < end:
        key, pos = decode_shortstr(data, pos)
        value, pos = decode_field_value(data, pos, depth=depth + 1, max_depth=max_depth)
        result[key] = value
    return result, end


PROTOCOL_HEADER = b"AMQP\x00\x00\x09\x01"
