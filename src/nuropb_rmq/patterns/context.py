"""Claims/context in AMQP headers (JWT). Spec-pure JSON-RPC body.

Requires optional extra: ``pip install -e ".[claims]"`` (PyJWT + cryptography).
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from nuropb_rmq.patterns.errors import (
    CLAIMS_EXPIRED,
    CLAIMS_MISSING,
    CLAIMS_UNBOUND,
    UNAUTHORIZED,
    RpcError,
    make_error_data,
)

CLAIMS_HEADER = "nr.claims"
CLAIMS_TYP_HEADER = "nr.claims_typ"
CLAIMS_TYP_JWT = "JWT"

AuthorizeFunc = Callable[[dict[str, Any], str, Any], bool]


def _require_jwt() -> Any:
    try:
        import jwt
    except ImportError as exc:
        raise RuntimeError(
            'JWT claims require optional dependency: pip install -e ".[claims]"'
        ) from exc
    return jwt


def attach_claims_headers(
    properties: dict[str, Any],
    token: str,
) -> dict[str, Any]:
    """Merge JWT claims into AMQP basic.properties headers (body untouched)."""
    if not token or not isinstance(token, str):
        raise ValueError("claims token must be a non-empty string")
    props = dict(properties)
    headers = dict(props.get("headers") or {})
    headers[CLAIMS_HEADER] = token
    headers[CLAIMS_TYP_HEADER] = CLAIMS_TYP_JWT
    props["headers"] = headers
    return props


@dataclass
class AuthConfig:
    """Fail-closed auth for RPC methods.

    Methods not listed in ``public_methods`` require a verified JWT.
    """

    # HS256 secret (bytes/str) and/or PEM public key for RS256/ES256
    jwt_secret: str | bytes | None = None
    jwt_public_key: str | bytes | None = None
    algorithms: tuple[str, ...] = ("HS256",)
    public_methods: frozenset[str] = field(default_factory=frozenset)
    authorize_func: AuthorizeFunc | None = None
    audience: str | None = None
    issuer: str | None = None

    def __post_init__(self) -> None:
        if self.jwt_secret is None and self.jwt_public_key is None:
            raise ValueError("AuthConfig requires jwt_secret and/or jwt_public_key")
        # Fail early if claims extra missing when auth is configured
        _require_jwt()

    def is_public(self, method: str) -> bool:
        return method in self.public_methods

    def _key_for_alg(self, alg: str) -> str | bytes:
        if alg.startswith("HS"):
            if self.jwt_secret is None:
                raise RpcError(
                    UNAUTHORIZED,
                    "HS* algorithm configured but jwt_secret missing",
                    make_error_data(code=UNAUTHORIZED),
                )
            return self.jwt_secret
        if self.jwt_public_key is None:
            raise RpcError(
                UNAUTHORIZED,
                "asymmetric algorithm configured but jwt_public_key missing",
                make_error_data(code=UNAUTHORIZED),
            )
        return self.jwt_public_key

    def verify_request(
        self,
        *,
        method: str,
        params: Any,
        correlation_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Return claims dict if auth OK; None if method is public.

        Raises RpcError on any failure (fail-closed).
        """
        if self.is_public(method):
            return None

        headers = properties.get("headers") or {}
        if not isinstance(headers, dict):
            raise RpcError(
                CLAIMS_MISSING,
                "claims headers missing",
                make_error_data(code=CLAIMS_MISSING, method=method, correlation_id=correlation_id),
            )

        typ = headers.get(CLAIMS_TYP_HEADER)
        token = headers.get(CLAIMS_HEADER)
        if typ is None and token is None:
            raise RpcError(
                CLAIMS_MISSING,
                "claims missing",
                make_error_data(code=CLAIMS_MISSING, method=method, correlation_id=correlation_id),
            )
        if typ != CLAIMS_TYP_JWT:
            raise RpcError(
                UNAUTHORIZED,
                "unsupported claims type",
                make_error_data(code=UNAUTHORIZED, method=method, correlation_id=correlation_id),
            )
        if not isinstance(token, str) or not token:
            raise RpcError(
                CLAIMS_MISSING,
                "claims token missing",
                make_error_data(code=CLAIMS_MISSING, method=method, correlation_id=correlation_id),
            )

        jwt = _require_jwt()
        options = {"require": ["exp", "jti", "method"]}
        kwargs: dict[str, Any] = {}
        if self.audience is not None:
            kwargs["audience"] = self.audience
        if self.issuer is not None:
            kwargs["issuer"] = self.issuer

        claims: dict[str, Any] | None = None
        last_err: Exception | None = None
        for alg in self.algorithms:
            try:
                key = self._key_for_alg(alg)
                claims = jwt.decode(
                    token,
                    key=key,
                    algorithms=[alg],
                    options=options,
                    **kwargs,
                )
                break
            except jwt.ExpiredSignatureError as exc:
                raise RpcError(
                    CLAIMS_EXPIRED,
                    "claims expired",
                    make_error_data(
                        code=CLAIMS_EXPIRED, method=method, correlation_id=correlation_id
                    ),
                ) from exc
            except jwt.InvalidTokenError as exc:
                last_err = exc
                continue

        if claims is None:
            raise RpcError(
                UNAUTHORIZED,
                "claims signature invalid",
                make_error_data(code=UNAUTHORIZED, method=method, correlation_id=correlation_id),
            ) from last_err

        jti = claims.get("jti")
        claim_method = claims.get("method")
        # Constant-time compare for binding fields
        if not isinstance(jti, str) or not hmac.compare_digest(jti, correlation_id):
            raise RpcError(
                CLAIMS_UNBOUND,
                "claims jti not bound to correlation id",
                make_error_data(
                    code=CLAIMS_UNBOUND, method=method, correlation_id=correlation_id
                ),
            )
        if not isinstance(claim_method, str) or not hmac.compare_digest(claim_method, method):
            raise RpcError(
                CLAIMS_UNBOUND,
                "claims method not bound to request method",
                make_error_data(
                    code=CLAIMS_UNBOUND, method=method, correlation_id=correlation_id
                ),
            )

        if self.authorize_func is not None:
            try:
                ok = self.authorize_func(claims, method, params)
            except Exception as exc:
                raise RpcError(
                    UNAUTHORIZED,
                    "authorize_func rejected request",
                    make_error_data(
                        code=UNAUTHORIZED, method=method, correlation_id=correlation_id
                    ),
                ) from exc
            if not ok:
                raise RpcError(
                    UNAUTHORIZED,
                    "authorize_func denied",
                    make_error_data(
                        code=UNAUTHORIZED, method=method, correlation_id=correlation_id
                    ),
                )
        return claims
