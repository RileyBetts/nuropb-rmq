"""Unit tests for JSON-RPC envelope and errors."""

from __future__ import annotations

import pytest

from nuropb_rmq.patterns.envelope import (
    decode_notification,
    decode_request,
    decode_response,
    encode_error,
    encode_notification,
    encode_request,
    encode_result,
)
from nuropb_rmq.patterns.errors import (
    REQUEST_TIMEOUT,
    RpcError,
    allowlist_error_data,
    make_error_data,
)


def test_request_roundtrip() -> None:
    body = encode_request("math.add", {"a": 1, "b": 2}, "abc")
    method, params, rid = decode_request(body)
    assert method == "math.add"
    assert params == {"a": 1, "b": 2}
    assert rid == "abc"


def test_notification_roundtrip() -> None:
    body = encode_notification("order.created", {"id": 7})
    method, params = decode_notification(body)
    assert method == "order.created"
    assert params == {"id": 7}
    assert b'"id"' not in body or b'"id":7' in body  # params may contain id key
    assert b'"jsonrpc":"2.0"' in body
    # Top-level id must be absent
    import json

    assert "id" not in json.loads(body)


def test_notification_rejects_request_with_id() -> None:
    body = encode_request("order.created", {}, "abc")
    with pytest.raises(RpcError, match="must not include id"):
        decode_notification(body)


def test_notification_rejects_response() -> None:
    body = encode_result({"ok": True}, "abc")
    with pytest.raises(RpcError, match="must not be a response"):
        decode_notification(body)


def test_result_roundtrip() -> None:
    body = encode_result({"sum": 3}, "abc")
    assert decode_response(body) == {"sum": 3}


def test_error_roundtrip_and_allowlist() -> None:
    data = make_error_data(code=REQUEST_TIMEOUT, retryable=True, correlation_id="abc", method="x")
    data["stack"] = "secret"  # type: ignore[index]  # should be stripped if passed through allowlist
    cleaned = allowlist_error_data(data)
    assert cleaned is not None
    assert "stack" not in cleaned
    body = encode_error(
        code=REQUEST_TIMEOUT,
        message="request timed out",
        request_id="abc",
        data={**cleaned, "hostname": "leak"},
    )
    with pytest.raises(RpcError) as ei:
        decode_response(body)
    assert ei.value.code == REQUEST_TIMEOUT
    assert ei.value.data is not None
    assert "hostname" not in ei.value.data
    assert ei.value.data.get("code_name") == "REQUEST_TIMEOUT"
