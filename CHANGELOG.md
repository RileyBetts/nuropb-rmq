# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Added

- Validated named queue profiles (`durable-at-least-once` default, `durable-classic`,
  `transient-fast-path`, `dlq-terminal`) with declare/publish enforcement
- Heartbeat send loop and missed-peer timeout → `CONNECTION_LOST`
- Public `nuropb_rmq.api` re-exports
- Ops doc for `reply-publish-restricted` permission profile
- SpeC++ Config CheckSat + Lean `NuropbRmq.Config` for durable↔delivery_mode
- Anti-enumeration content tests for allowlisted `error.data` shape
- Quorum `durable-at-least-once` RPC integration smoke

### Changed

- `RpcServer` / `MeshService` declare work queues via queue profiles (quorum by default)
- `EventPublisher` defaults to `transient-fast-path` delivery mode

## 0.1.0

- Initial Apache-2.0 library: native AMQP transport/protocol, Session/RPC,
  events, mesh, claims, reconnect, Lean/SpeC++ gates, AMQPS/mTLS, PEM TLS material
