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

GOLDEN_RS256_PUB = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAv5vGGwRn1wcRwSjqzxVJ\n"
    "mvfRRGOMioxCfqxSng8sXvM+lgSJDwQ8nF1xTTBP48Af/00QwxGmG1486QY4Q/9c\n"
    "NAvVuB/07pwKI+fD4OvZRCoUuwkFiYs6t6bO7osge3Jzzl5I1y08sVlpJ8/HnKpD\n"
    "TpCPeKcWoxFy5mwDraJuP4si9BvDOviMSJMOh8j+i5SUoN/lBmPJUj9kplDxemDk\n"
    "Cw9u/jOTBaiIwPQI6GbEiekjVGp5VAGQMit46NSQUbI2nX+HLMbQtsrcGTl/HxcY\n"
    "K7VO2ZpiPhSkH3n+0ZUHivpsdRMGyI1DyqKCgcqrlRcWCBjFfb9j9jFBw6793H80\n"
    "AwIDAQAB\n"
    "-----END PUBLIC KEY-----\n"
)
GOLDEN_RS256 = (
    "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJleHAiOjIwMDAwMDAwMDAsImp0aSI6ImNvcnItaWQtMDEiLCJtZXRob2QiOiJvcmRlcnMucGluZyJ9."
    "hYQWLaIhO22oQY1jQuURKYxO5z_s87ofbFfvPZpDLF36JBSYVIhPOwHDDLHeTrPU5BOo96s930AhHrHpZYJu-"
    "VrHdFprRBH9mOloP-aNjhvkiGWQkpiUuFyR2k2TRLqerIgqhGILzAry_wj90XEDXSPAVa4XzUMM6uJDVoDHHi"
    "yV9wNxGRXZilIg2XePakKuh68Yti4JHyCj_Du-7byXy60FCaIl8sQL_h1seuHfUuYqRQN2Rp-bNdreORpy1Gc"
    "xSpy6Mj5dEccxsnYxD6vyswX6tBD26sBMSev2e3II6iJZQ6h2NaCrkj7xnpEGuf6B80R5eAtXwgOqHJbYn66R4w"
)

GOLDEN_ES256_PUB = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEVE13xqh7qyP+5c5ta3rGYEPxaF20\n"
    "CvTALOGUFo+cYCOphrZkAN3RO5G84E55sKUsPArqBELP6iNgZACMuCmfcg==\n"
    "-----END PUBLIC KEY-----\n"
)
GOLDEN_ES256 = (
    "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJleHAiOjIwMDAwMDAwMDAsImp0aSI6ImNvcnItaWQtMDEiLCJtZXRob2QiOiJvcmRlcnMucGluZyJ9."
    "UIpa9vBktltZeATYBjoblQFZ4S7QYRVBdnPCsws1uJpAziRId2KveWVkKhUFzC1XPbzkRkF6_uKki-IU6tb48Q"
)


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


def test_golden_rs256_verify_request() -> None:
    pytest.importorskip("jwt")
    from nuropb_rmq.patterns.context import AuthConfig, attach_claims_headers

    auth = AuthConfig(jwt_public_key=GOLDEN_RS256_PUB, algorithms=("RS256",))
    auth.verify_request(
        method="orders.ping",
        params={},
        correlation_id="corr-id-01",
        properties=attach_claims_headers({}, GOLDEN_RS256),
    )


def test_golden_es256_verify_request() -> None:
    pytest.importorskip("jwt")
    from nuropb_rmq.patterns.context import AuthConfig, attach_claims_headers

    auth = AuthConfig(jwt_public_key=GOLDEN_ES256_PUB, algorithms=("ES256",))
    auth.verify_request(
        method="orders.ping",
        params={},
        correlation_id="corr-id-01",
        properties=attach_claims_headers({}, GOLDEN_ES256),
    )
