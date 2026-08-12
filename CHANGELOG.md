# Changelog

All notable changes to this project are documented in this file.

## Unreleased

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
- Docs: consumer-first README; CONTRIBUTING points at docs + examples

### Security

- TLS verify-full / mTLS paths; secrets-hook for material; JWT claim enforcement

