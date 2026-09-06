# Events: live bus vs durable fan-out

`EventPublisher` / `EventSubscriber` are a **pub/sub** path. They are not
mesh RPC. Durable at-least-once on **work queues** (`durable_at_least_once()`,
`MeshService`) is **competing consumers**: one backend wins each request.
That is the wrong topology for “every FIX message to every interested
consumer.”

RPC/mesh stays **off the critical performance path** (admin, claims,
control). Sequential hundreds of `RpcClient.request` calls on one `Session`
measure RTT, not fleet capacity.

## Two event profiles

| | Live (library default) | Durable fan-out (opt-in) |
|--|------------------------|---------------------------|
| Exchange | Non-durable, `auto_delete=True` | **Durable**, `auto_delete=False` |
| Publish | `transient-fast-path`, no confirm | Persistent + **publisher confirm** |
| Unroutable | Silent (`mandatory=False`) | `mandatory=True` (or an alternate-exchange) |
| Subscriber queue | Exclusive, auto-delete, broker-named | **Named durable queue per desk/service** |
| Offline consumer | Misses messages | Queue retains a copy |
| Reconnect | Caller restarts; no Session park | Queue backlog + ingest replay of unconfirmed publishes |

Defaults stay lossy so existing demos and the 1-sub/3-sub remasure do not
change. Trading ingest must **opt in**.

```python
from nuropb_rmq import EventPublisher, EventSubscriber, durable_classic

pub = EventPublisher(
    cfg, exchange="nr.fix.dropcopy", exchange_type="fanout",
    queue_profile=durable_classic(),  # persistent + confirm; durable exchange
)
await pub.start()

sub = EventSubscriber(
    cfg,
    exchange="nr.fix.dropcopy",
    exchange_type="fanout",
    queue="nr.fix.desk.a",  # required when durable
    durable=True,
    handler=on_fix,
)
await sub.start()
```

Passing a durable `queue_profile` on the publisher declares a **durable**
exchange and waits for confirm. It does **not** create per-desk queues —
each consumer must declare its **own** named durable queue. Two processes
on the **same** queue name are competing consumers (one copy), not
broadcast.

Lean: `EventPublisher.start` / `EventSubscriber.start` take
`durableExchange` / `wantConfirm` / `mandatory` and a named durable queue.
`publish` waits for confirm when `wantConfirm` is set.

## What “at least once” does not include

- Exactly-once delivery (duplicates are required; consumers must be
  idempotent on `ClOrdID` / `ExecID` / ingest seq)
- `dedup_window` (RPC-only, process-local)
- Session park-and-retry (RPC client futures only)
- Clustered broker loss unless each desk queue is quorum (expensive at N
  desks; start with `durable_classic()`)

## Ingest recipe (venue FIX → bus)

The library does not see the FIX TCP socket. The guarantee starts in
**lean-fix** (or any ingest process):

1. Receive and validate the FIX message (in-sequence).
2. **Do not treat it as received** (do not commit session seq / snapshot as
   durable fact) until either:
   - **A.** `EventPublisher.publish` returns after **publisher confirm** on
     the durable fan-out, or
   - **B.** A **local WAL / incremental log** records the wire, then publish
     asynchronously and **replay until confirm**.
3. Only then advance “received” for trading purposes.

**Do not** call lean-fix `persistState` / `snapshotOf` (full outbound store
rewrite) on every inbound message. The M3b file persist path was hundreds
of ops/s and will dominate the bus. Heartbeat-style debounce is not an
ingest WAL.

On `ConnectionBlockedError`, keep the FIX message in the local log and
retry; do not drop it.

Lean `EventSubscriber.receive` acks **after** a successful decode. Python
acks after a successful handler; decode failure is not acked. Raise
`NackDelivery` from a handler (or set `ack_on_error=False`) so a failed
app persist can requeue — do not ack-on-throw if the desk has not stored
the message.

See [queue profiles](queue-profiles.md), [reconnect](reconnect.md)
(RPC-only park), and [performance](performance.md) (many-to-many event
cells vs serial RPC).
