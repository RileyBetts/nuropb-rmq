# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Anti-enumeration: public error envelopes share allowlisted shape.

Architecture goal: DLQ timeout vs other mesh failures must not leak
distinguishing fields (queue names, hostnames, raw x-death) via error.data.
Timing indistinguishability remains a deployment/ops goal; this file locks
the content/shape half.
"""

from __future__ import annotations

import json

from nuropb_rmq.patterns.envelope import encode_error
from nuropb_rmq.patterns.errors import (
    REQUEST_TIMEOUT,
    SERVER_ERROR,
    allowlist_error_data,
    make_error_data,
)


def _error_obj(body: bytes) -> dict:
    payload = json.loads(body.decode("utf-8"))
    assert payload["jsonrpc"] == "2.0"
    assert "error" in payload
    return payload["error"]


def test_timeout_and_unknown_method_share_data_key_set() -> None:
    """Mesh-facing timeout vs coarse server error: same allowlisted data keys."""
    corr = "aabbccddeeff00112233445566778899"
    timeout = _error_obj(
        encode_error(
            code=REQUEST_TIMEOUT,
            message="request timed out",
            request_id=corr,
            data=make_error_data(
                code=REQUEST_TIMEOUT,
                retryable=True,
                correlation_id=corr,
                method="orders.ping",
            ),
        )
    )
    # Stand-in for “no such method” / unknown handler — same allowlist surface.
    unknown = _error_obj(
        encode_error(
            code=SERVER_ERROR,
            message="internal error",
            request_id=corr,
            data=make_error_data(
                code=SERVER_ERROR,
                retryable=False,
                correlation_id=corr,
                method="orders.ping",
            ),
        )
    )
    assert set(timeout["data"].keys()) == set(unknown["data"].keys())
    assert set(timeout["data"].keys()) <= {"code_name", "retryable", "correlation_id", "method"}
    for key in ("code", "message", "data"):
        assert key in timeout and key in unknown


def test_allowlist_strips_enumeration_leak_fields() -> None:
    dirty = {
        "code_name": "REQUEST_TIMEOUT",
        "retryable": True,
        "correlation_id": "abc",
        "method": "orders.ping",
        "queue": "nr.svc.orders",
        "hostname": "broker-1",
        "x-death": [{"queue": "nr.svc.orders"}],
        "stack": "traceback...",
    }
    cleaned = allowlist_error_data(dirty)
    assert cleaned is not None
    assert set(cleaned.keys()) == {"code_name", "retryable", "correlation_id", "method"}
    assert "queue" not in cleaned
    assert "hostname" not in cleaned
    assert "x-death" not in cleaned
    assert "stack" not in cleaned


def test_timeout_message_has_no_queue_or_host_leak() -> None:
    body = encode_error(
        code=REQUEST_TIMEOUT,
        message="request timed out",
        request_id="id1",
        data=make_error_data(code=REQUEST_TIMEOUT, retryable=True, correlation_id="id1"),
    )
    text = body.decode("utf-8").lower()
    assert "nr.svc" not in text
    assert "x-death" not in text
    assert "localhost" not in text
    assert "127.0.0.1" not in text
