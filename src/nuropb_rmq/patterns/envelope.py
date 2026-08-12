# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""JSON-RPC 2.0 envelope encode/decode (spec-pure body)."""

from __future__ import annotations

import json
from typing import Any

from nuropb_rmq.patterns.errors import (
    INVALID_ENVELOPE,
    RpcError,
    allowlist_error_data,
    make_error_data,
)


def encode_request(method: str, params: Any, request_id: str) -> bytes:
    return json.dumps(
        {"jsonrpc": "2.0", "method": method, "params": params, "id": request_id},
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def encode_result(result: Any, request_id: str) -> bytes:
    return json.dumps(
        {"jsonrpc": "2.0", "result": result, "id": request_id},
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def encode_error(
    *,
    code: int,
    message: str,
    request_id: str | None,
    data: dict[str, Any] | None = None,
) -> bytes:
    err: dict[str, Any] = {"code": code, "message": message}
    cleaned = allowlist_error_data(data)
    if cleaned:
        err["data"] = cleaned
    return json.dumps(
        {"jsonrpc": "2.0", "error": err, "id": request_id},
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def decode_message(body: bytes) -> dict[str, Any]:
    try:
        msg = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RpcError(
            INVALID_ENVELOPE,
            "invalid JSON-RPC body",
            make_error_data(code=INVALID_ENVELOPE),
        ) from exc
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        raise RpcError(
            INVALID_ENVELOPE,
            "jsonrpc version must be 2.0",
            make_error_data(code=INVALID_ENVELOPE),
        )
    return msg


def decode_request(body: bytes) -> tuple[str, Any, str]:
    msg = decode_message(body)
    method = msg.get("method")
    request_id = msg.get("id")
    if not isinstance(method, str) or not isinstance(request_id, str):
        raise RpcError(
            INVALID_ENVELOPE,
            "request requires string method and id",
            make_error_data(code=INVALID_ENVELOPE),
        )
    return method, msg.get("params"), request_id


def encode_notification(method: str, params: Any = None) -> bytes:
    """JSON-RPC 2.0 notification: request shape without `id`."""
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def decode_notification(body: bytes) -> tuple[str, Any]:
    """Decode a notification; reject responses and id-bearing requests."""
    msg = decode_message(body)
    if "result" in msg or "error" in msg:
        raise RpcError(
            INVALID_ENVELOPE,
            "notification must not be a response",
            make_error_data(code=INVALID_ENVELOPE),
        )
    if "id" in msg:
        raise RpcError(
            INVALID_ENVELOPE,
            "notification must not include id",
            make_error_data(code=INVALID_ENVELOPE),
        )
    method = msg.get("method")
    if not isinstance(method, str):
        raise RpcError(
            INVALID_ENVELOPE,
            "notification requires string method",
            make_error_data(code=INVALID_ENVELOPE),
        )
    return method, msg.get("params")


def decode_response(body: bytes) -> Any:
    msg = decode_message(body)
    request_id = msg.get("id")
    rid = request_id if isinstance(request_id, str) else None
    if "result" in msg:
        return msg["result"]
    if "error" in msg and isinstance(msg["error"], dict):
        err = msg["error"]
        raise RpcError(
            int(err.get("code", -32000)),
            str(err.get("message", "error")),
            allowlist_error_data(err.get("data") if isinstance(err.get("data"), dict) else None),
            id=rid,
        )
    raise RpcError(
        INVALID_ENVELOPE,
        "response missing result/error",
        make_error_data(code=INVALID_ENVELOPE),
        id=rid,
    )
