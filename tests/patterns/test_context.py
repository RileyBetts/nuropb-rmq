# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Unit tests for JWT claims attach/verify (requires [claims] extra)."""

from __future__ import annotations

import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

pytest.importorskip("jwt")
import jwt

from nuropb_rmq.patterns.context import AuthConfig, attach_claims_headers
from nuropb_rmq.patterns.errors import (
    CLAIMS_EXPIRED,
    CLAIMS_MISSING,
    CLAIMS_UNBOUND,
    UNAUTHORIZED,
    RpcError,
)

SECRET = "test-secret-key-for-hs256-32bytes!"  # 32+ bytes for HS256



def _token(*, jti: str, method: str, exp_delta: int = 60, **extra: object) -> str:
    payload = {
        "jti": jti,
        "method": method,
        "exp": int(time.time()) + exp_delta,
        **extra,
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def test_attach_claims_headers() -> None:
    props = attach_claims_headers({"content_type": "application/json"}, "tok.en")
    assert props["headers"]["nr.claims"] == "tok.en"
    assert props["headers"]["nr.claims_typ"] == "JWT"
    assert "nr.claims" not in (props.get("content_type") or "")


def test_verify_ok() -> None:
    auth = AuthConfig(jwt_secret=SECRET, algorithms=("HS256",))
    tok = _token(jti="abc", method="orders.ping")
    claims = auth.verify_request(
        method="orders.ping",
        params={},
        correlation_id="abc",
        properties={"headers": {"nr.claims": tok, "nr.claims_typ": "JWT"}},
    )
    assert claims is not None
    assert claims["jti"] == "abc"


def test_public_method_skips_claims() -> None:
    auth = AuthConfig(
        jwt_secret=SECRET,
        algorithms=("HS256",),
        public_methods=frozenset({"health.check"}),
    )
    assert (
        auth.verify_request(
            method="health.check",
            params={},
            correlation_id="x",
            properties={},
        )
        is None
    )


def test_missing_claims_fail_closed() -> None:
    auth = AuthConfig(jwt_secret=SECRET)
    with pytest.raises(RpcError) as ei:
        auth.verify_request(
            method="orders.ping",
            params={},
            correlation_id="abc",
            properties={},
        )
    assert ei.value.code == CLAIMS_MISSING


def test_expired_claims() -> None:
    auth = AuthConfig(jwt_secret=SECRET)
    tok = _token(jti="abc", method="orders.ping", exp_delta=-10)
    with pytest.raises(RpcError) as ei:
        auth.verify_request(
            method="orders.ping",
            params={},
            correlation_id="abc",
            properties={"headers": {"nr.claims": tok, "nr.claims_typ": "JWT"}},
        )
    assert ei.value.code == CLAIMS_EXPIRED


def test_jti_unbound() -> None:
    auth = AuthConfig(jwt_secret=SECRET)
    tok = _token(jti="other", method="orders.ping")
    with pytest.raises(RpcError) as ei:
        auth.verify_request(
            method="orders.ping",
            params={},
            correlation_id="abc",
            properties={"headers": {"nr.claims": tok, "nr.claims_typ": "JWT"}},
        )
    assert ei.value.code == CLAIMS_UNBOUND


def test_method_unbound() -> None:
    auth = AuthConfig(jwt_secret=SECRET)
    tok = _token(jti="abc", method="orders.other")
    with pytest.raises(RpcError) as ei:
        auth.verify_request(
            method="orders.ping",
            params={},
            correlation_id="abc",
            properties={"headers": {"nr.claims": tok, "nr.claims_typ": "JWT"}},
        )
    assert ei.value.code == CLAIMS_UNBOUND


def test_bad_signature() -> None:
    auth = AuthConfig(jwt_secret=SECRET)
    tok = jwt.encode(
        {"jti": "abc", "method": "orders.ping", "exp": int(time.time()) + 60},
        "wrong-secret-also-long-enough-32b!",
        algorithm="HS256",
    )
    with pytest.raises(RpcError) as ei:
        auth.verify_request(
            method="orders.ping",
            params={},
            correlation_id="abc",
            properties={"headers": {"nr.claims": tok, "nr.claims_typ": "JWT"}},
        )
    assert ei.value.code == UNAUTHORIZED


def test_authorize_func_denied() -> None:
    auth = AuthConfig(
        jwt_secret=SECRET,
        authorize_func=lambda claims, method, params: False,
    )
    tok = _token(jti="abc", method="orders.ping")
    with pytest.raises(RpcError) as ei:
        auth.verify_request(
            method="orders.ping",
            params={},
            correlation_id="abc",
            properties={"headers": {"nr.claims": tok, "nr.claims_typ": "JWT"}},
        )
    assert ei.value.code == UNAUTHORIZED


@given(st.text(alphabet="abcdef0123456789", min_size=8, max_size=32))
@settings(max_examples=20)
def test_pbt_jti_must_match(corr: str) -> None:
    auth = AuthConfig(jwt_secret=SECRET)
    tok = _token(jti=corr, method="m.x")
    auth.verify_request(
        method="m.x",
        params=None,
        correlation_id=corr,
        properties={"headers": {"nr.claims": tok, "nr.claims_typ": "JWT"}},
    )
    with pytest.raises(RpcError):
        auth.verify_request(
            method="m.x",
            params=None,
            correlation_id=corr + "z",
            properties={"headers": {"nr.claims": tok, "nr.claims_typ": "JWT"}},
        )


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz.", min_size=1, max_size=24))
@settings(max_examples=20)
def test_pbt_public_skip(method: str) -> None:
    """Lean `tryAuth_public_skip`: public methods need no claims."""
    auth = AuthConfig(
        jwt_secret=SECRET,
        algorithms=("HS256",),
        public_methods=frozenset({method}),
    )
    assert (
        auth.verify_request(
            method=method,
            params={},
            correlation_id="any",
            properties={},
        )
        is None
    )
