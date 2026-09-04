# Roadmap

Dated **2026-09-04**. Python 1.0 (`src/nuropb_rmq/api.py`) stays frozen. This
is not a release schedule and does not claim Reservoir tags or a new PyPI
version.

## Done on `development`

- Optional process-local RPC request-id dedup (`dedup_window` / Lean
  `tryDedup`): handler at most once; park delivery stays at-least-once
- Lean RS256/ES256 verify on `NuropbRMQTls` (OpenSSL FFI + PyJWT goldens)
- Lean `authorize_func`: opaque `authorizeOk` on `tryAuth`, optional RPC hook
  after HS256 (deny/allow in Lean claims smoke)
- Scoped Lean/Python `matchesRegex` for documented ACL profiles plus a live
  narrower-than-prefix regex 403 (not RabbitMQ's full engine / HA)
- Dual runtime: Lean POSIX client (`import NuropbRMQ`) shares SpeC++ / Lean
  kernels with Python; no extraction either way
- PLAIN mesh + optional AMQPS (`NuropbRMQTls.connect`, tls-verify-full PEM)
- mTLS PEM + PKCS#12 + SASL `EXTERNAL` (`NuropbRMQTls.connect` + `selectSasl`;
  still not default `lake build`)
- Smokes: `scripts/smoke_interop.sh`, `smoke_lean_amqps.sh`,
  `smoke_lean_coverage.sh`, `smoke_lean_mtls.sh`, `smoke_lean_reply_acl.sh`,
  `smoke_lean_jwt_asymmetric.sh`, `smoke_lean_reply_acl_regex.sh`
  (claims, events, DLQ, park/fail-fast reconnect, `lean_dedup_hello`,
  live `amq.default` 403, narrower regex 403, mTLS EXTERNAL)
- CI: `lean`, `lean-interop` (includes reply-forge 403 + regex 403), `lean-amqps`,
  `lean-mtls` (not required for merge except `Lean NuropbRMQSpec + NuropbRMQ`)

## Next (Lean IO)

_(empty — Lean IO residuals below)_

## Not claimed

- HMAC/SHA-256 hardness
- Full RabbitMQ regex engine / HA (scoped `matchesRegex` + live 403 are done)
- Park exactly-once *delivery* / clustered dedup (optional in-process
  `dedup_window` is handler-once only)
- LangChain / LangGraph in Lean (examples stay Python-only)
- Default `lake build` without OpenSSL (mTLS / PKCS#12 stay on `NuropbRMQTls`)

See [CHANGELOG Unreleased](../CHANGELOG.md), [testing regime](reference/testing-regime.md),
and [CORRESPONDENCE](../specs/lean/CORRESPONDENCE.md).
