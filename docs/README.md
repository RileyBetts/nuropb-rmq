# User documentation

Guides for **integrators and operators** deploying `nuropb-rmq` against
RabbitMQ (local, cloud, or enterprise AMQPS).

| Tree | Audience | Role |
|------|----------|------|
| [`docs/`](.) | Users / operators | How to configure and deploy |
| [`thinking/`](../thinking/) | Maintainers | Design decisions and specs that drive new features |
| [`scripts/*.md`](../scripts/reply-publish-restricted.md) | Ops | Checklists next to broker conf examples |

Start here if you are wiring the library into an app. Use `thinking/` only when
you need the decision ledger or formal-methods correspondence.

## Concepts

- [Architecture overview](concepts/architecture-overview.md) — layers and Mermaid diagrams
- [Connection config](concepts/connection-config.md) — `ConnectionConfig` mental model
- [TLS profiles and material](concepts/tls-profiles-and-material.md) — AMQPS trust and certs
- [Queue profiles](concepts/queue-profiles.md) — durable defaults and publish rules
- [Reconnect](concepts/reconnect.md) — fail-fast `CONNECTION_LOST` and rebind
- [Service mesh](concepts/service-mesh.md) — what “mesh” means in this library
- [JWT claims](concepts/jwt-claims.md) — application auth on RPC headers

## Guides

- [Cloud and enterprise AMQPS](guides/cloud-and-enterprise-amqps.md)
- [Local AMQPS harness](guides/amqps-local.md)
- [Broker permissions](guides/broker-permissions.md) — reply-publish + mesh-bind

## Reference

- [ConnectionConfig fields](reference/connection-config.md)
- [Environment variables](reference/env-vars.md) — `NUROPB_RMQ_*` in examples/tests

## Also see

- [Root README](../README.md) — install and quick start
- [CHANGELOG](../CHANGELOG.md)
- [CONTRIBUTING](../CONTRIBUTING.md)
