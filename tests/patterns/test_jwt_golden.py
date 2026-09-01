# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""PyJWT golden token ↔ Lean ``Pattern.Jwt.goldenToken`` correspondence."""

from __future__ import annotations

import hashlib
import hmac

import pytest

GOLDEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJleHAiOjIwMDAwMDAwMDAsImp0aSI6ImNvcnItaWQtMDEiLCJtZXRob2QiOiJvcmRlcnMucGluZyJ9."
    "2rsdzXvOcSa21j8nUHDxV0B4v_163qqxsITHhpuozeg"
)
SECRET = "test-secret"


def test_golden_hmac_matches_compact_sig() -> None:
    header, payload, sig_b64 = GOLDEN.split(".")
    mac = hmac.new(SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    import base64

    raw = base64.urlsafe_b64decode(sig_b64 + "==")
    assert hmac.compare_digest(mac, raw)


def test_golden_verify_request() -> None:
    pytest.importorskip("jwt")
    from nuropb_rmq.patterns.context import AuthConfig, attach_claims_headers

    auth = AuthConfig(jwt_secret=SECRET, algorithms=("HS256",))
    auth.verify_request(
        method="orders.ping",
        params={},
        correlation_id="corr-id-01",
        properties=attach_claims_headers({}, GOLDEN),
    )
