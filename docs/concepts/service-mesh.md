# Service mesh (in nuropb-rmq)

“Mesh” here means **application-level JSON-RPC 2.0 over a shared RabbitMQ
broker** — not a Kubernetes sidecar mesh (Istio, Linkerd, Cilium service mesh,
and so on).

## What it is

- Named services register under a **`ServiceIdentity`** and bind routing keys
  of the form `service.method` on the mesh exchange (default `nr.mesh`).
- Clients call methods via **Session / `RpcClient`** (JSON-RPC request/response)
  with exclusive reply queues.
- Optional **events** use the JSON-RPC notification shape over topic/fanout.
- Optional **discovery**: `MeshService(..., announce=True)` publishes an
  advertisement on fanout `nr.mesh.registry`; `MeshRegistryViewer` lists/lookups
  with TTL.

The broker plus its ACLs are the fabric. The library provides patterns and
client-side guardrails on top of native AMQP.

## What it is not

- No sidecar proxy or data-plane interceptor
- No L7 traffic policy / mTLS mesh identity from a control plane
- No replacement for broker permissions — discovery never authorizes binds

## Layers (runtime)

```text
Application
  → Pattern (MeshService, RpcClient/Server, events, claims)
    → Session (correlation, reply queues, reconnect coordination)
      → Protocol + Transport (AMQP 0-9-1 over asyncio TCP/TLS)
```

Diagrams: [Architecture overview](architecture-overview.md).

## Namespaced bind

Permission profile name: **`mesh-bind-namespaced`**.

- The broker user should only bind/consume under `<service>.*`.
- `MeshService` refuses out-of-namespace binds client-side (`assert_bind_allowed`).
- **Broker ACL remains the hard gate.**

After reconnect, call `mesh.rebind()` and restart consumers — see
[Reconnect](reconnect.md).

## Retry authority (LangGraph / long-running clients)

The library does **not** park-and-retry in-flight RPCs across reconnect.
Ownership is split so there is one authoritative retry path:

| Layer | Owns |
|-------|------|
| Mesh / RabbitMQ | Redelivery while the client's exclusive reply queue still exists |
| Application / adapter | `CONNECTION_LOST` → new session epoch → `mesh.rebind()` |
| LangGraph (if used) | Checkpoint replay of the failed node after rebind, **new correlation id** |
| Handler | Idempotency (at-least-once + replay can run a method more than once) |

Adapters stay **out of the core package**. LangChain/LangGraph wrappers live
under [`examples/`](../../examples/) so those dependencies never enter
`nuropb-rmq`. Operator walkthrough: [Using nuropb-rmq under LangGraph](../guides/langgraph.md).

A misrouted mesh/RPC publish surfaces as `PUBLISH_RETURNED` (`basic.return`),
not a hang until TTL.

## Discovery vs authorization

| Mechanism | Role |
|-----------|------|
| Broker ACL + `assert_bind_allowed` | Bind / consume authorization |
| `nr.mesh.registry` announce/viewer | Discovery aid only |

## Example

```python
from nuropb_rmq import MeshRegistryViewer, MeshService, ServiceIdentity

mesh = MeshService(
    cfg,
    identity=ServiceIdentity("orders"),
    methods=["ping"],
    announce=True,
)
await mesh.start()
viewer = MeshRegistryViewer(cfg)
await viewer.start()
print(viewer.lookup("orders"))
```

Runnable walkthroughs:

- Mesh RPC + events + registry:
  [`examples/one_client_one_service/`](../../examples/one_client_one_service/)
- LangChain tool over mesh RPC:
  [`examples/langchain_example/`](../../examples/langchain_example/)
- LangGraph remote node over mesh RPC:
  [`examples/langgraph_example/`](../../examples/langgraph_example/)

## Related

- [JWT claims](jwt-claims.md) — application auth on RPC
- [Broker permissions](../guides/broker-permissions.md)
- Ops checklist: [`scripts/reply-publish-restricted.md`](../../scripts/reply-publish-restricted.md)
