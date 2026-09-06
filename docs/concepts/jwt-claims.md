# JWT claims

Optional application-level authorization for RPC. Claims travel in **AMQP
headers**; the JSON-RPC body stays spec-pure.

Install the extra:

```bash
pip install 'nuropb-rmq[claims]'
# or: uv sync --extra claims
```

## Headers

| Header | Type | Value |
|--------|------|-------|
| `nr.claims` | longstr | JWS compact JWT |
| `nr.claims_typ` | shortstr | Always `JWT` in v1 |

Attach on the client with `RpcClient`’s `claims_token=` argument or
`attach_claims_headers(properties, token)`.

## Required claims (auth-required methods)

| Claim | Binding |
|-------|---------|
| `exp` | Expiry (required) |
| `jti` | Must equal the request **correlation id** |
| `method` | Must equal the RPC **method** name |

Verification is **fail-closed**: missing, expired, unbound, or invalid
signatures raise `RpcError` — there is no anonymous fallback for methods that
require auth.

Methods listed in `AuthConfig.public_methods` skip claims.

## AuthConfig

```python
from nuropb_rmq import AuthConfig, RpcServer

auth = AuthConfig(
    jwt_secret=b"shared-hs256-secret",
    algorithms=("HS256",),
    public_methods=frozenset({"health"}),
    # optional: jwt_public_key=..., audience=..., issuer=..., authorize_func=...
)
server = RpcServer(cfg, queue="orders", handler=handler, auth=auth)
```

- Provide `jwt_secret` (HS*) and/or `jwt_public_key` (RS*/ES*).
- Python `AuthConfig` verifies HS256 and RS256/ES256 via PyJWT (`[claims]`
  extra; goldens in `test_jwt_golden.py`). Lean HS256 is
  `Pattern.Jwt.verifyHs256` (libc). Lean RS256/ES256 is
  `NuropbRMQ.Tls.verifyRs256` / `verifyEs256` (`import NuropbRMQTls`; OpenSSL).
- Optional `authorize_func(claims, method, params) -> bool` for app policy after
  signature and binding checks. Lean `AuthConfig.authorize` is the same hook
  (`false` or exception → `UNAUTHORIZED`).
- Constant-time compares are used for `jti` / `method` binding.

## Error codes (sketch)

| Code family | Examples |
|-------------|----------|
| Authorization / claims | `UNAUTHORIZED`, `CLAIMS_MISSING`, `CLAIMS_EXPIRED`, `CLAIMS_UNBOUND` |

## TLS vs claims

| Layer | Question answered |
|-------|-------------------|
| TLS / mTLS / SASL | Is this **connection** talking to the right broker (and maybe client cert)? |
| JWT claims | Is this **RPC** allowed for this method / correlation? |

Both may apply. mTLS identity does not replace JWT claims, and vice versa.

## Diagram

See [Architecture overview — Claims on the wire](architecture-overview.md#claims-on-the-wire).

## Related

- Implementation: `src/nuropb_rmq/patterns/context.py`
- [Service mesh](service-mesh.md)
- Tests: `tests/patterns/test_context.py` (needs `[claims]` extra)
