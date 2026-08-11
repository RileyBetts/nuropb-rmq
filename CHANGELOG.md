# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Added

- PKCS#12 (`.p12`/`.pfx`) TLS material via `pkcs12_file` / `pkcs12_data` (+ optional password);
  optional `[pkcs12]` extra (`cryptography`); normalizes to PEM `TlsMaterial`
- Optional AMQP mesh discovery registry (`nr.mesh.registry` fanout):
  `MeshService(announce=True)`, `MeshRegistryPublisher` / `MeshRegistryViewer`
- Example `examples/one_client_one_service/` — one client + one service (RPC, events,
  registry discovery)
- Examples `examples/vanilla_hello/` and `examples/vanilla_topic/` — plain
  `AmqpConnection` publish/consume and topic pub/sub
- `scripts/smoke_examples.sh` — local smoke runner for all example suites
- uv as project manager: committed `uv.lock`, `.python-version` (3.12), PEP 735
  `dev` dependency group; product extras remain `claims` / `pkcs12` / `bench`

### Fixed

- Field-value decode raises `AmqpCodecError` on truncated fixed-width tags
  (fuzz found `IndexError` on lone `t` / similar short payloads)

## 0.1.0 — 2026-08-11

First tagged library surface (Apache-2.0).

### Added

- Native AMQP 0-9-1 transport/protocol (no runtime `pika`)
- Session/RPC (exclusive reply queues), events, mesh bind, JWT claims
- Fail-fast reconnect (`CONNECTION_LOST`); Lean Phase 1 / 1b / 2 + Pattern proofs
- SpeC++ CheckSat (Protocol / Session / Pattern / Phase 2 / Config)
- Throughput harness vs pika (`[bench]` extra)
- AMQPS `tls-verify-full` + mTLS/`EXTERNAL`; PEM cert sourcing (files / bytes / secrets hook)
- Named queue profiles (`durable-at-least-once` default) + Config Lean
- Heartbeat send + missed-peer watchdog
- Public `nuropb_rmq.api` re-exports; reply-publish-restricted ops doc
- Anti-enumeration content tests; dedicated frame-decode fuzz CI lane (`pytest -m fuzz`)

### Changed

- `RpcServer` / `MeshService` declare via queue profiles (quorum by default)
- `EventPublisher` defaults to `transient-fast-path` delivery mode

## Release checklist (`v0.1.0`)

Do **not** publish to PyPI until explicitly requested. For a GitHub release:

1. Gates green on `main`: SpeC++, unit (excl. fuzz), fuzz (`HYPOTHESIS_PROFILE=ci`), claims, integration, Lean
2. `git tag -a v0.1.0 -m "nuropb-rmq 0.1.0"`
3. `git push origin main --tags` (only when asked to push)
4. `gh release create v0.1.0 --notes-file CHANGELOG.md` (or paste the 0.1.0 section)
