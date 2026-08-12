# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""AMQP 0-9-1 method (de)serialization for connection/channel/queue/basic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nuropb_rmq.transport.frame import (
    AmqpCodecError,
    decode_longstr,
    decode_shortstr,
    decode_table,
    encode_longstr,
    encode_shortstr,
    encode_table,
)


@dataclass(frozen=True, slots=True)
class Method:
    class_id: int
    method_id: int
    args: dict[str, Any]


# class / method ids
CONNECTION = 10
CHANNEL = 20
EXCHANGE = 40
QUEUE = 50
BASIC = 60

CONNECTION_START = 10
CONNECTION_START_OK = 11
CONNECTION_SECURE = 20
CONNECTION_SECURE_OK = 21
CONNECTION_TUNE = 30
CONNECTION_TUNE_OK = 31
CONNECTION_OPEN = 40
CONNECTION_OPEN_OK = 41
CONNECTION_CLOSE = 50
CONNECTION_CLOSE_OK = 51
CONNECTION_BLOCKED = 60
CONNECTION_UNBLOCKED = 61

CHANNEL_OPEN = 10
CHANNEL_OPEN_OK = 11
CHANNEL_CLOSE = 40
CHANNEL_CLOSE_OK = 41

QUEUE_DECLARE = 10
QUEUE_DECLARE_OK = 11
QUEUE_BIND = 20
QUEUE_BIND_OK = 21

EXCHANGE_DECLARE = 10
EXCHANGE_DECLARE_OK = 11

BASIC_PUBLISH = 40
BASIC_CONSUME = 20
BASIC_CONSUME_OK = 21
BASIC_CANCEL = 30
BASIC_CANCEL_OK = 31
BASIC_DELIVER = 60
BASIC_ACK = 80
BASIC_REJECT = 90
BASIC_NACK = 120
BASIC_QOS = 10
BASIC_QOS_OK = 11

# RabbitMQ confirm extension (class 85)
CONFIRM = 85
CONFIRM_SELECT = 10
CONFIRM_SELECT_OK = 11


def encode_method(method: Method) -> bytes:
    body = method.class_id.to_bytes(2, "big") + method.method_id.to_bytes(2, "big")
    args = method.args
    cid, mid = method.class_id, method.method_id

    if cid == CONNECTION and mid == CONNECTION_START_OK:
        body += encode_table(args.get("client_properties", {}))
        body += encode_shortstr(args["mechanism"])
        body += encode_longstr(args["response"])
        body += encode_shortstr(args.get("locale", "en_US"))
    elif cid == CONNECTION and mid == CONNECTION_TUNE_OK:
        body += int(args["channel_max"]).to_bytes(2, "big")
        body += int(args["frame_max"]).to_bytes(4, "big")
        body += int(args["heartbeat"]).to_bytes(2, "big")
    elif cid == CONNECTION and mid == CONNECTION_OPEN:
        body += encode_shortstr(args.get("virtual_host", "/"))
        body += encode_shortstr(args.get("capabilities", ""))
        body += bytes([1 if args.get("insist", False) else 0])
    elif cid == CONNECTION and mid == CONNECTION_CLOSE:
        body += int(args.get("reply_code", 200)).to_bytes(2, "big")
        body += encode_shortstr(args.get("reply_text", ""))
        body += int(args.get("class_id", 0)).to_bytes(2, "big")
        body += int(args.get("method_id", 0)).to_bytes(2, "big")
    elif cid == CONNECTION and mid == CONNECTION_CLOSE_OK:
        pass
    elif cid == CHANNEL and mid == CHANNEL_OPEN:
        body += encode_shortstr(args.get("out_of_band", ""))
    elif cid == CHANNEL and mid == CHANNEL_OPEN_OK:
        body += encode_longstr(args.get("channel_id", b""))
    elif cid == CHANNEL and mid == CHANNEL_CLOSE:
        body += int(args.get("reply_code", 200)).to_bytes(2, "big")
        body += encode_shortstr(args.get("reply_text", ""))
        body += int(args.get("class_id", 0)).to_bytes(2, "big")
        body += int(args.get("method_id", 0)).to_bytes(2, "big")
    elif cid == CHANNEL and mid == CHANNEL_CLOSE_OK:
        pass
    elif cid == QUEUE and mid == QUEUE_DECLARE:
        body += int(args.get("ticket", 0)).to_bytes(2, "big")
        body += encode_shortstr(args.get("queue", ""))
        bits = 0
        if args.get("passive"):
            bits |= 1
        if args.get("durable"):
            bits |= 2
        if args.get("exclusive"):
            bits |= 4
        if args.get("auto_delete"):
            bits |= 8
        if args.get("nowait"):
            bits |= 16
        body += bytes([bits])
        body += encode_table(args.get("arguments", {}))
    elif cid == EXCHANGE and mid == EXCHANGE_DECLARE:
        body += int(args.get("ticket", 0)).to_bytes(2, "big")
        body += encode_shortstr(args["exchange"])
        body += encode_shortstr(args.get("type", "direct"))
        bits = 0
        if args.get("passive"):
            bits |= 1
        if args.get("durable"):
            bits |= 2
        if args.get("auto_delete"):
            bits |= 4
        if args.get("internal"):
            bits |= 8
        if args.get("nowait"):
            bits |= 16
        body += bytes([bits])
        body += encode_table(args.get("arguments", {}))
    elif cid == QUEUE and mid == QUEUE_BIND:
        body += int(args.get("ticket", 0)).to_bytes(2, "big")
        body += encode_shortstr(args.get("queue", ""))
        body += encode_shortstr(args.get("exchange", ""))
        body += encode_shortstr(args.get("routing_key", ""))
        body += bytes([1 if args.get("nowait") else 0])
        body += encode_table(args.get("arguments", {}))
    elif cid == BASIC and mid == BASIC_PUBLISH:
        body += int(args.get("ticket", 0)).to_bytes(2, "big")
        body += encode_shortstr(args.get("exchange", ""))
        body += encode_shortstr(args.get("routing_key", ""))
        bits = 0
        if args.get("mandatory"):
            bits |= 1
        if args.get("immediate"):
            bits |= 2
        body += bytes([bits])
    elif cid == BASIC and mid == BASIC_CONSUME:
        body += int(args.get("ticket", 0)).to_bytes(2, "big")
        body += encode_shortstr(args.get("queue", ""))
        body += encode_shortstr(args.get("consumer_tag", ""))
        bits = 0
        if args.get("no_local"):
            bits |= 1
        if args.get("no_ack"):
            bits |= 2
        if args.get("exclusive"):
            bits |= 4
        if args.get("nowait"):
            bits |= 8
        body += bytes([bits])
        body += encode_table(args.get("arguments", {}))
    elif cid == BASIC and mid == BASIC_ACK:
        body += int(args["delivery_tag"]).to_bytes(8, "big")
        body += bytes([1 if args.get("multiple") else 0])
    elif cid == BASIC and mid == BASIC_REJECT:
        body += int(args["delivery_tag"]).to_bytes(8, "big")
        body += bytes([1 if args.get("requeue") else 0])
    elif cid == BASIC and mid == BASIC_NACK:
        body += int(args["delivery_tag"]).to_bytes(8, "big")
        bits = 0
        if args.get("multiple"):
            bits |= 1
        if args.get("requeue"):
            bits |= 2
        body += bytes([bits])
    elif cid == BASIC and mid == BASIC_CANCEL:
        body += encode_shortstr(args.get("consumer_tag", ""))
        body += bytes([1 if args.get("nowait") else 0])
    elif cid == BASIC and mid == BASIC_QOS:
        body += int(args.get("prefetch_size", 0)).to_bytes(4, "big")
        body += int(args.get("prefetch_count", 0)).to_bytes(2, "big")
        body += bytes([1 if args.get("global_") else 0])
    elif cid == CONFIRM and mid == CONFIRM_SELECT:
        body += bytes([1 if args.get("nowait") else 0])
    else:
        raise AmqpCodecError(f"encode unsupported method {cid}.{mid}")
    return body


def decode_method(payload: bytes) -> Method:
    if len(payload) < 4:
        raise AmqpCodecError("method payload too short")
    class_id = int.from_bytes(payload[0:2], "big")
    method_id = int.from_bytes(payload[2:4], "big")
    offset = 4
    args: dict[str, Any] = {}

    if class_id == CONNECTION and method_id == CONNECTION_START:
        args["version_major"] = payload[offset]
        args["version_minor"] = payload[offset + 1]
        offset += 2
        args["server_properties"], offset = decode_table(payload, offset)
        mechanisms, offset = decode_longstr(payload, offset)
        args["mechanisms"] = mechanisms.decode("utf-8")
        locales, offset = decode_longstr(payload, offset)
        args["locales"] = locales.decode("utf-8")
    elif class_id == CONNECTION and method_id == CONNECTION_TUNE:
        args["channel_max"] = int.from_bytes(payload[offset : offset + 2], "big")
        args["frame_max"] = int.from_bytes(payload[offset + 2 : offset + 6], "big")
        args["heartbeat"] = int.from_bytes(payload[offset + 6 : offset + 8], "big")
    elif class_id == CONNECTION and method_id == CONNECTION_OPEN_OK:
        args["reserved_1"], _ = decode_shortstr(payload, offset)
    elif class_id == CONNECTION and method_id == CONNECTION_CLOSE:
        args["reply_code"] = int.from_bytes(payload[offset : offset + 2], "big")
        offset += 2
        args["reply_text"], offset = decode_shortstr(payload, offset)
        args["class_id"] = int.from_bytes(payload[offset : offset + 2], "big")
        args["method_id"] = int.from_bytes(payload[offset + 2 : offset + 4], "big")
    elif class_id == CONNECTION and method_id == CONNECTION_CLOSE_OK:
        pass
    elif class_id == CHANNEL and method_id == CHANNEL_OPEN_OK:
        args["channel_id"], _ = decode_longstr(payload, offset)
    elif class_id == CHANNEL and method_id == CHANNEL_CLOSE:
        args["reply_code"] = int.from_bytes(payload[offset : offset + 2], "big")
        offset += 2
        args["reply_text"], offset = decode_shortstr(payload, offset)
        args["class_id"] = int.from_bytes(payload[offset : offset + 2], "big")
        args["method_id"] = int.from_bytes(payload[offset + 2 : offset + 4], "big")
    elif class_id == CHANNEL and method_id == CHANNEL_CLOSE_OK:
        pass
    elif class_id == QUEUE and method_id == QUEUE_DECLARE_OK:
        args["queue"], offset = decode_shortstr(payload, offset)
        args["message_count"] = int.from_bytes(payload[offset : offset + 4], "big")
        args["consumer_count"] = int.from_bytes(payload[offset + 4 : offset + 8], "big")
    elif class_id == EXCHANGE and method_id == EXCHANGE_DECLARE_OK:
        pass
    elif class_id == QUEUE and method_id == QUEUE_BIND_OK:
        pass
    elif class_id == BASIC and method_id == BASIC_CONSUME_OK:
        args["consumer_tag"], _ = decode_shortstr(payload, offset)
    elif class_id == BASIC and method_id == BASIC_DELIVER:
        args["consumer_tag"], offset = decode_shortstr(payload, offset)
        args["delivery_tag"] = int.from_bytes(payload[offset : offset + 8], "big")
        offset += 8
        args["redelivered"] = bool(payload[offset])
        offset += 1
        args["exchange"], offset = decode_shortstr(payload, offset)
        args["routing_key"], offset = decode_shortstr(payload, offset)
    elif class_id == BASIC and method_id == BASIC_QOS_OK:
        pass
    elif class_id == BASIC and method_id == BASIC_CANCEL_OK:
        args["consumer_tag"], _ = decode_shortstr(payload, offset)
    elif class_id == BASIC and method_id == BASIC_ACK:
        args["delivery_tag"] = int.from_bytes(payload[offset : offset + 8], "big")
        args["multiple"] = bool(payload[offset + 8]) if offset + 9 <= len(payload) else False
    elif class_id == BASIC and method_id == BASIC_NACK:
        args["delivery_tag"] = int.from_bytes(payload[offset : offset + 8], "big")
        bits = payload[offset + 8] if offset + 9 <= len(payload) else 0
        args["multiple"] = bool(bits & 1)
        args["requeue"] = bool(bits & 2)
    elif class_id == CONNECTION and method_id == CONNECTION_BLOCKED:
        args["reason"], _ = decode_shortstr(payload, offset)
    elif class_id == CONNECTION and method_id == CONNECTION_UNBLOCKED:
        pass
    elif class_id == CONNECTION and method_id == CONNECTION_SECURE:
        args["challenge"], _ = decode_longstr(payload, offset)
    elif class_id == CONFIRM and method_id == CONFIRM_SELECT_OK:
        pass
    else:
        # Unknown inbound method: keep raw for diagnostics without failing closed here;
        # connection SM decides legality.
        args["raw"] = payload[4:]
    return Method(class_id=class_id, method_id=method_id, args=args)


def encode_content_header(
    *,
    class_id: int,
    body_size: int,
    properties: dict[str, Any] | None = None,
) -> bytes:
    """Encode basic content header (class 60)."""
    props = properties or {}
    # property flags bit order for basic (AMQP 0-9-1):
    # 15 content-type, 14 content-encoding, 13 headers, 12 delivery-mode,
    # 11 priority, 10 correlation-id, 9 reply-to, 8 expiration,
    # 7 message-id, 6 timestamp, 5 type, 4 user-id, 3 app-id, 2 cluster-id
    flags = 0
    prop_body = bytearray()
    if "content_type" in props:
        flags |= 1 << 15
        prop_body += encode_shortstr(props["content_type"])
    if "content_encoding" in props:
        flags |= 1 << 14
        prop_body += encode_shortstr(props["content_encoding"])
    if "headers" in props:
        flags |= 1 << 13
        prop_body += encode_table(props["headers"])
    if "delivery_mode" in props:
        flags |= 1 << 12
        prop_body += bytes([int(props["delivery_mode"])])
    if "priority" in props:
        flags |= 1 << 11
        prop_body += bytes([int(props["priority"])])
    if "correlation_id" in props:
        flags |= 1 << 10
        prop_body += encode_shortstr(props["correlation_id"])
    if "reply_to" in props:
        flags |= 1 << 9
        prop_body += encode_shortstr(props["reply_to"])
    if "expiration" in props:
        flags |= 1 << 8
        prop_body += encode_shortstr(props["expiration"])
    if "message_id" in props:
        flags |= 1 << 7
        prop_body += encode_shortstr(props["message_id"])
    return (
        class_id.to_bytes(2, "big")
        + (0).to_bytes(2, "big")  # weight
        + body_size.to_bytes(8, "big")
        + flags.to_bytes(2, "big")
        + bytes(prop_body)
    )


def decode_content_header(payload: bytes) -> tuple[int, int, dict[str, Any]]:
    if len(payload) < 14:
        raise AmqpCodecError("content header too short")
    class_id = int.from_bytes(payload[0:2], "big")
    body_size = int.from_bytes(payload[4:12], "big")
    flags = int.from_bytes(payload[12:14], "big")
    offset = 14
    props: dict[str, Any] = {}
    if flags & (1 << 15):
        props["content_type"], offset = decode_shortstr(payload, offset)
    if flags & (1 << 14):
        props["content_encoding"], offset = decode_shortstr(payload, offset)
    if flags & (1 << 13):
        props["headers"], offset = decode_table(payload, offset)
    if flags & (1 << 12):
        props["delivery_mode"] = payload[offset]
        offset += 1
    if flags & (1 << 11):
        props["priority"] = payload[offset]
        offset += 1
    if flags & (1 << 10):
        props["correlation_id"], offset = decode_shortstr(payload, offset)
    if flags & (1 << 9):
        props["reply_to"], offset = decode_shortstr(payload, offset)
    if flags & (1 << 8):
        props["expiration"], offset = decode_shortstr(payload, offset)
    if flags & (1 << 7):
        props["message_id"], offset = decode_shortstr(payload, offset)
    return class_id, body_size, props
