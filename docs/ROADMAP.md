# Roadmap

Dated **2026-09-04**. Python 1.0 (`src/nuropb_rmq/api.py`) stays frozen. This
is not a release schedule and does not claim Reservoir tags or a new PyPI
version.

## Done on `development`

- Dual runtime: Lean POSIX client (`import NuropbRMQ`) shares SpeC++ / Lean
  kernels with Python; no extraction either way
- PLAIN mesh + optional AMQPS (`NuropbRMQTls.connect`, tls-verify-full PEM)
- mTLS PEM + SASL `EXTERNAL` (`NuropbRMQTls.connect` + `selectSasl`; still
  not default `lake build`)
- Smokes: `scripts/smoke_interop.sh`, `smoke_lean_amqps.sh`,
  `smoke_lean_coverage.sh`, `smoke_lean_mtls.sh`, `smoke_lean_reply_acl.sh`
  (claims, events, DLQ, park/fail-fast reconnect, live `amq.default` 403,
  mTLS EXTERNAL)
- CI: `lean`, `lean-interop` (includes reply-forge 403), `lean-amqps`,
  `lean-mtls` (not required for merge except `Lean NuropbRMQSpec + NuropbRMQ`)

## Next (Lean IO)

- PKCS#12 client material in `NuropbRMQTls` / OpenSSL FFI only

## Not claimed

- HMAC/SHA-256 hardness; RS256/ES256
- Lean `authorize_func`
- RabbitMQ regex ACL engine (prefixes + live `amq.default` 403 in Python and Lean)
- Park **exactly-once** server execution (at-least-once)
- LangChain / LangGraph in Lean (examples stay Python-only)

See [CHANGELOG Unreleased](../CHANGELOG.md), [testing regime](reference/testing-regime.md),
and [CORRESPONDENCE](../specs/lean/CORRESPONDENCE.md).
