# Roadmap

Dated **2026-09-04**. Python 1.0 (`src/nuropb_rmq/api.py`) stays frozen. This
is not a release schedule and does not claim Reservoir tags or a new PyPI
version.

## Done on `development`

- Lean RS256/ES256 verify on `NuropbRMQTls` (OpenSSL FFI + PyJWT goldens)
- Lean `authorize_func`: opaque `authorizeOk` on `tryAuth`, optional RPC hook
  after HS256 (deny/allow in Lean claims smoke)
- Dual runtime: Lean POSIX client (`import NuropbRMQ`) shares SpeC++ / Lean
  kernels with Python; no extraction either way
- PLAIN mesh + optional AMQPS (`NuropbRMQTls.connect`, tls-verify-full PEM)
- mTLS PEM + PKCS#12 + SASL `EXTERNAL` (`NuropbRMQTls.connect` + `selectSasl`;
  still not default `lake build`)
- Smokes: `scripts/smoke_interop.sh`, `smoke_lean_amqps.sh`,
  `smoke_lean_coverage.sh`, `smoke_lean_mtls.sh`, `smoke_lean_reply_acl.sh`,
  `smoke_lean_jwt_asymmetric.sh`
  (claims, events, DLQ, park/fail-fast reconnect, live `amq.default` 403,
  mTLS EXTERNAL)
- CI: `lean`, `lean-interop` (includes reply-forge 403), `lean-amqps`,
  `lean-mtls` (not required for merge except `Lean NuropbRMQSpec + NuropbRMQ`)

## Next (Lean IO)

_(empty — Lean IO residuals below)_

## Not claimed

- HMAC/SHA-256 hardness
- RabbitMQ regex ACL engine (prefixes + live `amq.default` 403 in Python and Lean)
- Park **exactly-once** server execution (at-least-once)
- LangChain / LangGraph in Lean (examples stay Python-only)
- Default `lake build` without OpenSSL (mTLS / PKCS#12 stay on `NuropbRMQTls`)

See [CHANGELOG Unreleased](../CHANGELOG.md), [testing regime](reference/testing-regime.md),
and [CORRESPONDENCE](../specs/lean/CORRESPONDENCE.md).
