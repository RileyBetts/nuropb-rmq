# Roadmap

Dated **2026-09-04**. Python 1.0 (`src/nuropb_rmq/api.py`) stays frozen. This
is not a release schedule and does not claim Reservoir tags or a new PyPI
version.

## Done on `development`

- Dual runtime: Lean POSIX client (`import NuropbRMQ`) shares SpeC++ / Lean
  kernels with Python; no extraction either way
- PLAIN mesh + optional AMQPS (`NuropbRMQTls.connect`, tls-verify-full PEM)
- Smokes: `scripts/smoke_interop.sh`, `smoke_lean_amqps.sh`,
  `smoke_lean_coverage.sh` (claims, events, DLQ, park/fail-fast reconnect)
- CI: `lean`, `lean-interop`, `lean-amqps` (not required for merge except
  `Lean NuropbRMQSpec + NuropbRMQ`)

## Next (Lean IO)

- mTLS PEM + SASL `EXTERNAL` (reuse `scripts/gen_amqps_certs.sh` and the
  Python mTLS broker conf). Still not default `lake build`
- PKCS#12 client material in `NuropbRMQTls` / OpenSSL FFI only
- Lean live reply-forge 403 (Python/script may create management-API users)

## Not claimed

- HMAC/SHA-256 hardness; RS256/ES256
- Lean `authorize_func`
- RabbitMQ regex ACL engine (prefixes + live `amq.default` 403 in Python)
- Park **exactly-once** server execution (at-least-once)
- LangChain / LangGraph in Lean (examples stay Python-only)

See [CHANGELOG Unreleased](../CHANGELOG.md), [testing regime](reference/testing-regime.md),
and [CORRESPONDENCE](../specs/lean/CORRESPONDENCE.md).
