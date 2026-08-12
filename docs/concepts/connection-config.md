# Connection config

All connections start from `ConnectionConfig` (public import:
`from nuropb_rmq import ConnectionConfig`).

## Mental model

| Concern | Fields |
|---------|--------|
| Where | `host`, `port`, `virtual_host` |
| Who (broker user) | `username`, `password` |
| Liveness | `heartbeat` (seconds; client watchdog uses 2× interval) |
| Framing | `frame_max` |
| TLS | `tls`, `tls_profile`, material slots, `server_hostname`, `custom_sans` |

Defaults target a local open broker: `127.0.0.1:5672`, vhost `/`, `guest`/`guest`,
`heartbeat=60`, `tls=False`.

## No built-in env loader

The library does **not** read environment variables itself. Examples and
integration tests map `NUROPB_RMQ_*` into `ConnectionConfig` in your process —
see [Environment variables](../reference/env-vars.md).

```python
from nuropb_rmq import AmqpConnection, ConnectionConfig

cfg = ConnectionConfig(
    host="rmq.example.com",
    port=5671,
    virtual_host="/prod",
    username="app-client",
    password="…",
    tls=True,
    tls_profile="tls-verify-full",
    ca_file="/etc/ssl/certs/rmq-ca.pem",
    server_hostname="rmq.example.com",
)
conn = AmqpConnection(cfg)
await conn.connect()
```

## Host vs server hostname

- **`host`** — TCP dial target (IP, private DNS, load balancer).
- **`server_hostname`** — name used for TLS SNI and certificate hostname checks
  (falls back to `host` when unset).

Cloud and LB setups often need them to differ. See
[Cloud and enterprise AMQPS](../guides/cloud-and-enterprise-amqps.md).

## Related

- Field table: [ConnectionConfig reference](../reference/connection-config.md)
- TLS details: [TLS profiles and material](tls-profiles-and-material.md)
- Diagram: [Architecture overview — AMQPS connect](architecture-overview.md#amqps-connect)
- Under broker memory/disk alarm, `connection.blocked` sets a fail-fast flag:
  further `basic_publish` raises `ConnectionBlockedError` until `unblocked`
  (optional `on_connection_blocked` / `on_connection_unblocked` callbacks).
