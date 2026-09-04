# User documentation

Guides for **integrators and operators** deploying `nuropb-rmq` against
RabbitMQ (local, cloud, or enterprise AMQPS).

| Tree | Audience | Role |
|------|----------|------|
| [`docs/`](.) | Users / operators | How to configure and deploy |
| [`scripts/*.md`](../scripts/reply-publish-restricted.md) | Ops | Checklists next to broker conf examples |

Start here if you are wiring the library into an app. Formal-methods
correspondence for contributors is in [`specs/lean/CORRESPONDENCE.md`](../specs/lean/CORRESPONDENCE.md).

## Concepts

- [Architecture overview](concepts/architecture-overview.md) — layers and Mermaid diagrams
- [Connection config](concepts/connection-config.md) — `ConnectionConfig` mental model
- [TLS profiles and material](concepts/tls-profiles-and-material.md) — AMQPS trust and certs
- [Queue profiles](concepts/queue-profiles.md) — durable defaults and publish rules
- [Reconnect](concepts/reconnect.md) — park-and-retry default; fail-fast opt-in
- [Performance](concepts/performance.md) — bench vs pika; raw vs RPC how to read
- [API stability](reference/api-stability.md) — 1.0 freeze surface
- [Service mesh](concepts/service-mesh.md) — what “mesh” means in this library
- [JWT claims](concepts/jwt-claims.md) — application auth on RPC headers

## Guides

- [Cloud and enterprise AMQPS](guides/cloud-and-enterprise-amqps.md)
- [Local AMQPS harness](guides/amqps-local.md)
- [Broker permissions](guides/broker-permissions.md) — reply-publish + mesh-bind
- [Using nuropb-rmq under LangGraph](guides/langgraph.md) — retry authority, adapters stay in examples

## Reference

- [ConnectionConfig fields](reference/connection-config.md)
- [Environment variables](reference/env-vars.md) — `NUROPB_RMQ_*` in examples/tests
- [Testing regime](reference/testing-regime.md) — proof and test layers, attack surfaces
- [Roadmap](ROADMAP.md) — done on `development`, next Lean IO, residuals

## Examples

Runnable demos under [`examples/`](../examples/). Smoke all suites with
[`scripts/smoke_examples.sh`](../scripts/smoke_examples.sh). Lean ↔ Python interop:
[`scripts/smoke_interop.sh`](../scripts/smoke_interop.sh). LangChain / LangGraph
suites need `uv sync` in their example directories first. They stay Python-only.

| Example | Shows |
|---------|--------|
| [vanilla_hello](../examples/vanilla_hello/) | Durable publish/consume |
| [vanilla_topic](../examples/vanilla_topic/) | Topic pub/sub |
| [one_client_one_service](../examples/one_client_one_service/) | Mesh RPC + events + registry |
| [lean_mesh](../examples/lean_mesh/) | Lean ↔ Lean mesh (`import NuropbRMQ`) |
| [interop_hello](../examples/interop_hello/) | Lean ↔ Python durable queue both directions |
| [interop_mesh](../examples/interop_mesh/) | Lean ↔ Python mesh RPC/events both directions |
| [langchain_example](../examples/langchain_example/) | LangChain tool → `orders.get_status` mesh RPC (Python-only) |
| [langgraph_example](../examples/langgraph_example/) | LangGraph `remote_node` invoice extract + reconnect replay (Python-only) |

## Also see

- [Root README](../README.md) — install and quick start
- [CHANGELOG](../CHANGELOG.md)
- [Roadmap](ROADMAP.md)
- [CONTRIBUTING](../CONTRIBUTING.md)
