# Reconnect

**Default (1.0):** park-and-retry. In-flight `RpcClient` futures stay pending
across a connection drop. After a new epoch and exclusive reply queue, the
library republishes with the same correlation id and the new `reply_to`. First
reply on the new queue completes the existing Future.

Republish is **at-least-once delivery** on the server. Handlers must be
idempotent, callers opt into fail-fast, or the server sets optional
`dedup_window` (process-local request-id cache: handler at most once; the
replay replies with the cached success payload). Failures are not cached.
This is not clustered / HA dedup and does not survive process restart.

**Fail-fast:** `Session(..., fail_outstanding=True)` or
`ReconnectPolicy(fail_outstanding=True)` completes outstanding RPCs with
`CONNECTION_LOST` immediately (0.5.x behaviour).

## Behaviour

1. On disconnect, default policy **parks** outstanding RPCs (does not complete
   them). Fail-fast completes them with `CONNECTION_LOST`.
2. A new connection opens a new **epoch** and a new exclusive reply queue.
   Parked requests are republished automatically (Session auto-reconnect uses
   `ReconnectCoordinator` backoff). If attempts are exhausted, parked futures
   fail with `CONNECTION_LOST`.
3. Mesh consumers must be **rebound and restarted by the caller**.
   Park-and-retry is client RPC only.

```python
from nuropb_rmq import ReconnectCoordinator, ReconnectPolicy, RpcServer, Session

# Default: park-and-retry
session = Session(cfg)
await session.start()

# Opt into 0.5.x fail-fast
session = Session(cfg, fail_outstanding=True)

await ReconnectCoordinator().reconnect(session)
await mesh.rebind()
server = RpcServer.from_mesh(mesh, handler=handler)  # or dedup_window=32
await server.start()
```

## Why park is the default

A dropped TCP connection should not require every `await client.request(...)`
to be retried by the application with a new correlation id. The Future you
already hold is the one client-visible completion. The server may *deliver* the request twice if the original delivery already
ran — that is at-least-once, not exactly-once delivery. Optional
`RpcServer(..., dedup_window=N)` skips a second handler call for the same
request id in this process.

## Diagram

See [Architecture overview — Reconnect](architecture-overview.md#reconnect).

## Related

- [Service mesh](service-mesh.md) — `MeshService.rebind`
- TLS material is re-resolved on each `connect()` when using `tls_secrets`
- [API stability](../reference/api-stability.md) — `ReconnectPolicy`
- LangGraph example (adapters stay in `examples/`):
  [`examples/langgraph_example/reconnect_demo.py`](../../examples/langgraph_example/reconnect_demo.py)
