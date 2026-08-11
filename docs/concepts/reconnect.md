# Reconnect

v1 reconnect is **fail-fast**. There is no silent park-and-retry of in-flight
RPCs across a connection loss.

## Behaviour

1. On disconnect, outstanding RPCs fail with `CONNECTION_LOST`.
2. A new connection opens a new **epoch** and a new exclusive reply queue.
3. Mesh consumers must be **rebound and restarted by the caller**.

```python
from nuropb_rmq import ReconnectCoordinator, RpcServer

await ReconnectCoordinator().reconnect(session)
await mesh.rebind()
server = RpcServer.from_mesh(mesh, handler=handler)
await server.start()
```

## Why fail-fast

Park-and-retry across reconnect would create multi-path outcomes for the same
correlation id. The architecture keeps one authoritative path: fail the
outstanding call; the application decides whether to retry on the new epoch.

## Diagram

See [Architecture overview — Reconnect](architecture-overview.md#reconnect-v1).

## Related

- [Service mesh](service-mesh.md) — `MeshService.rebind`
- TLS material is re-resolved on each `connect()` when using `tls_secrets`
