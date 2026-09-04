# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Added

- Lean POSIX AMQP/mesh client (`import NuropbRMQ`) on the same kernels as the
  frozen Python 1.0 API. Default `lake build` is libc only (no OpenSSL)
- Optional AMQPS via `NuropbRMQTls.connect` / `Transport` (`tls-verify-full` PEM)
- Lean ↔ Python interop, Lean AMQPS, Lean IO coverage, and Lean reply-forge 403
  smokes (`scripts/smoke_interop.sh`, `smoke_lean_amqps.sh`,
  `smoke_lean_coverage.sh`, `smoke_lean_reply_acl.sh`,
  `smoke_lean_reply_acl_regex.sh`, `smoke_lean_mtls.sh`,
  `smoke_lean_jwt_asymmetric.sh`)
- CI jobs: `lean`, `lean-interop` (includes coverage + 403), `lean-amqps`,
  `lean-mtls` (mTLS PEM + SASL `EXTERNAL`; not required to merge)
- Lean SASL `EXTERNAL` when the broker offers it and a client PEM pair or
  PKCS#12 bag is set (`NuropbRMQTls` / OpenSSL FFI only)
- Lean RS256/ES256 JWT verify on `NuropbRMQTls` / OpenSSL FFI (PyJWT goldens;
  default `lake build` stays libc / HS256)
- Scoped `matchesRegex` (Lean + Python) for documented ACL profiles as regex,
  plus a live narrower-than-prefix regex 403; full broker engine stays residual
- Lean `authorize_func`: opaque `authorizeOk` on `tryAuth`, optional RPC hook
  after HS256 (`claims → method → params → Bool`); deny/allow in Lean claims smoke
- Proof hygiene: channel `allowsOps`, `Reachable` witnesses, `wellFormedPark`,
  `Ids.validId`, TLS oracle vector; field decode of DLQ `x-death` arrays
- Python unit holes: `ConnectionBlockedError` inject, `NackDelivery`,
  `MeshRegistryPublisher` via `api`, AMQPS wrong-hostname
- Project roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md)

### Honesty

- Park republish remains at-least-once (not exactly-once)
- Default `lake build` does not link OpenSSL (PKCS#12 / mTLS / RS256/ES256 stay
  on `NuropbRMQTls` only)
- HMAC hardness and the full RabbitMQ regex engine / HA stay residual

## 1.0.0 — 2026-09-01

### Added

- Park-and-retry reconnect is the **default**: in-flight `RpcClient` futures
  survive a drop, republish with the new exclusive `reply_to`. Fail-fast remains
  `ReconnectPolicy(fail_outstanding=True)` / `Session(fail_outstanding=True)`
- Lean: executable HS256 JWT compact verify (PyJWT golden token) and nuropb ACL
  profiles (`reply-publish-restricted`, `mesh-bind-namespaced`)
- Lean / SpeC++: `connection.update-secret` legalSend, `connection.blocked`
  refuse-publish, heartbeat miss-count → lost, `basic.return` then confirm-ack,
  park epoch invariants
- CI: AMQPS `tls-verify-full` job; management-API reply-publish ACL; example smoke
- Public API freeze (`docs/reference/api-stability.md`), error constants and
  `ReconnectPolicy` / `NamespaceError` on `nuropb_rmq.api`
- `py.typed`; `client_properties.version` from `__version__`
- Documented the SpeC++ / Lean / PBT / live testing regime and attack surfaces
  (`docs/reference/testing-regime.md`)
- Performance note vs pika (raw/fanout vs exclusive-reply RPC) in
  [`docs/concepts/performance.md`](docs/concepts/performance.md)

### Changed

- Classifier `Development Status :: 5 - Production/Stable`
- `reply-publish-restricted` client **write** no longer includes `nr.reply.*`
  (forge denied is now a theorem + CI)

### Honesty

- Park republish is at-least-once (not exactly-once)
- Lean JWT is HS256 decision procedure, not HMAC hardness or RS256/ES256
- Broker ACL model is nuropb prefixes, not RabbitMQ's regex engine.
  Live `reply-publish-restricted` correspondence waits for `channel.close` 403
  and grants service **write** on `amq.default` (default-exchange `reply_to`).
- mTLS / SASL EXTERNAL remains opt-in (not the AMQPS CI job)

## 0.5.0 — 2026-08-15

### Added

- `basic.return` / optional `mandatory` on `basic_publish`; unroutable publishes
  raise `PublishReturned` (distinct from `PublishNack` / confirms)
- `RpcClient` publishes with `mandatory=true` so a missing target is an error,
  not a silent hang (`PUBLISH_RETURNED`)
- `DlqTimeoutProcessor` publishes timeout replies with `mandatory=true` and
  counts unroutable drops (`unroutable_replies`) without changing the drop
- AMQP content properties `timestamp`, `type`, `user_id`, `app_id`, `cluster_id`
- `AmqpConnection.update_secret` (`connection.update-secret` thin round-trip)
- SpeC++ / Lean: `basic_return` (return ≠ confirm nack)
- Docs: retry-authority on the service mesh page; LangGraph operator guide
  (`docs/guides/langgraph.md`); adapters remain example-local
- Unit-test coverage measurement (`pytest-cov`) in CI — `--cov-fail-under=50`
  on the unit lane (regression floor; integration job covers live transport)
- Alpha→beta criteria in `CONTRIBUTING.md`

### Changed

- Queue-profile docs: unroutable/mandatory vs confirms; non-goals unchanged
  (`basic.get`, Tx, Access, `channel.flow`, delete/unbind/purge)

## 0.4.1 — 2026-08-12

### Added

- Automated PyPI publish on annotated `v*` tags (Trusted Publishing /
  `.github/workflows/publish.yml`); CI `uv build` + `twine check`

## 0.3.0 — 2026-08-12

### Added

- Examples: `langchain_example/` — LangChain agent calling mesh service tool
  `orders.get_status` (self-standing uv project)
- Examples: `langgraph_example/` — LangGraph remote invoice extract via
  `remote_node` + optional reconnect/replay demo (self-standing uv project)
- `scripts/smoke_examples.sh` covers both new suites (happy-path / `--smoke`)

### Fixed

- Rename misspelled example directory `langraph_example` → `langgraph_example`

## 0.2.0 — 2026-08-12

### Added

- Publisher confirms (`confirm.select`); durable profile / RPC publishes wait for
  broker ack/nack (`PublishNack`, `PUBLISH_NACK`)
- `connection.blocked` / `unblocked` handling with fail-fast publish refusal
  (`ConnectionBlockedError`); unexpected `connection.secure` rejects
- Outbound BODY frame fragmentation; `frame_max` bounds total wire size (payload+8)
- `basic.nack` / `basic.reject` / `basic.cancel`; `NackDelivery` for RpcServer poison path
- Field-table encoder support for float, list/array, Decimal, datetime
- SpeC++ + Lean: frame bounds, publisher confirms, delivery settle
- Copyright / Apache-2.0 headers on Lean, Python, SMT-LIB, and shell source files

### Changed

- Docs: queue-profile durability now documents confirms + nack→DLX; explicit AMQP non-goals

## 0.1.0 — 2026-08-11

First tagged **alpha** library surface (Apache-2.0). Public API is relatively
stable; expect polish and docs before a broader 0.1.x / PyPI push.

### Added

- Native AMQP 0-9-1 transport/protocol (no runtime `pika`)
- Session/RPC (exclusive reply queues), events, mesh bind, JWT claims
- Fail-fast reconnect (`CONNECTION_LOST`); Lean Phase 1 / 1b / 2 + Pattern proofs
- SpeC++ CheckSat (Protocol / Session / Pattern / Phase 2 / Config)
- Throughput harness vs pika (`[bench]` extra)
- AMQPS `tls-verify-full` + mTLS/`EXTERNAL`; PEM + PKCS#12 + secrets-hook material
- Named queue profiles (`durable-at-least-once` default) + Config Lean
- Heartbeat send + missed-peer watchdog
- Public `nuropb_rmq.api` re-exports; reply-publish-restricted ops doc
- Anti-enumeration content tests; dedicated frame-decode fuzz CI lane (`pytest -m fuzz`)
- Optional AMQP mesh discovery registry (`nr.mesh.registry` fanout):
  `MeshService(announce=True)`, `MeshRegistryPublisher` / `MeshRegistryViewer`
- Examples: `one_client_one_service/`, `vanilla_hello/`, `vanilla_topic/`
- `scripts/smoke_examples.sh` — local smoke runner for all example suites
- uv as project manager: committed `uv.lock`, `.python-version` (3.12), PEP 735
  `dev` dependency group; product extras `claims` / `pkcs12` / `bench`
- User-facing [`docs/`](docs/README.md): architecture diagrams, connection/TLS/queue
  concepts, service mesh + JWT claims, cloud/enterprise AMQPS and broker-permission
  guides

### Changed

- `RpcServer` / `MeshService` declare via queue profiles (quorum by default)
- `EventPublisher` defaults to `transient-fast-path` delivery mode
- README consumer-first; maintainer branching/CI in [`CONTRIBUTING.md`](CONTRIBUTING.md);
  capability detail pointed at `docs/`

### Fixed

- Field-value decode raises `AmqpCodecError` on truncated fixed-width tags
  (fuzz found `IndexError` on lone `t` / similar short payloads)

## Release checklist

For a GitHub + PyPI release:

1. Gates green on `main`: SpeC++, unit (excl. fuzz), fuzz (`HYPOTHESIS_PROFILE=ci`), claims, integration, Lean, package build
2. Bump `pyproject.toml` / `__version__` (and AMQP `client_properties.version`) to `X.Y.Z`; fold CHANGELOG
3. Promote `development` → `main` (merge commit)
4. `git tag -a vX.Y.Z -m "nuropb-rmq X.Y.Z"` and `git push origin vX.Y.Z`
   — [`.github/workflows/publish.yml`](.github/workflows/publish.yml) builds and uploads to PyPI
5. `gh release create vX.Y.Z --notes-file …` (or paste the matching CHANGELOG section)

One-time Trusted Publisher setup: see [`CONTRIBUTING.md`](CONTRIBUTING.md#publishing).
