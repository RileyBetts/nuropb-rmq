# Broker permissions

Two deployment profiles matter for mesh RPC. The library documents the
required shape; **RabbitMQ ACLs are the hard gate**.

## `mesh-bind-namespaced`

Bind/consume only under the service identity’s `<service>.*` routing-key
namespace. `MeshService` also refuses out-of-namespace binds client-side —
that is a guardrail, not a substitute for broker permissions.

See [Service mesh](../concepts/service-mesh.md).

## `reply-publish-restricted`

Clients declare exclusive reply queues named `nr.reply.<connection_id>`.
Any publisher that can write to those queues can forge RPC replies.

| Actor | Needs |
|-------|-------|
| Mesh / RPC **services** | May **publish** to `nr.reply.*` when completing requests. On RabbitMQ this includes **write** on `amq.default` (the nameless default exchange used for `reply_to`). |
| Ordinary **clients** | May **declare/consume** their own `nr.reply.*` queues; must **not** have `write` on `amq.default` / `nr.reply.*` (forge denied). |
| Shared `guest` / `write=.*` | Avoid for untrusted users |

Full rabbitmqctl sketches and ops checklist:
[`scripts/reply-publish-restricted.md`](../../scripts/reply-publish-restricted.md).

## Discovery is not authorization

Optional `MeshService(announce=True)` / `MeshRegistryViewer` on
`nr.mesh.registry` only helps discovery. Bind gates remain broker ACL +
`assert_bind_allowed`.

## Related

- [Architecture — Mesh RPC path](../concepts/architecture-overview.md#mesh-rpc-path)
- [Cloud and enterprise AMQPS](cloud-and-enterprise-amqps.md)
