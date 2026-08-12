# Queue profiles

Work queues are declared with a validated **`QueueProfile`**: durability,
queue type, delivery mode, TTL/DLX, and delivery-limit travel together so a
durable queue never silently accepts non-persistent publishes.

## Built-in profiles

| Factory | Name | Notes |
|---------|------|-------|
| `durable_at_least_once()` | **Default** for RpcServer / Mesh | Quorum + persistent + TTL + DLX + `x-delivery-limit` |
| `durable_classic()` | Classic durable | Persistent + TTL/DLX; no delivery-limit |
| `transient_fast_path()` | Classic non-durable | Lossy; never a silent default for work queues |
| `dlq_terminal()` | Durable classic DLQ | No further dead-lettering |

```python
from nuropb_rmq import RpcServer, durable_classic

server = RpcServer(cfg, queue="orders", handler=handler, queue_profile=durable_classic())
```

## Rules

- Durable profiles require `delivery_mode=2` (persistent); publish refuses a mismatch.
- Quorum profiles require `x-delivery-limit`; classic forbids it.
- TTL and dead-letter exchange must be set together when either is used.
- **Session reply queues** stay exclusive / auto-delete / ephemeral — they do
  not use the work-queue profile.
- **Publisher confirms:** publishing with a durable `QueueProfile` (and Session/RPC
  requests) enables RabbitMQ `confirm.select` and waits for broker ack/nack before
  `basic_publish` returns. Persistent bits alone are not a producer-side durability
  guarantee.
- **Poison messages:** handlers may raise `NackDelivery` (or call `basic_nack` with
  `requeue=False`) so the broker can dead-letter via the profile DLX — TTL /
  delivery-limit are not the only path.

## Related

- Config / Lean notes: `thinking/architecture.md` (Configuration Strategy)
- Public imports: `durable_at_least_once`, `durable_classic`, …
- Non-goals (deliberate): `basic.get`, Tx class, Access, channel.flow,
  exchange/queue delete/unbind/purge — continuous consume + declare-own-topology
  only.
