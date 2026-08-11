# Cloud and enterprise AMQPS

Practical patterns for deploying `nuropb-rmq` against managed or enterprise
RabbitMQ over TLS. Provider-agnostic — adjust hostnames and ports to your
vendor console.

## Baseline client settings

```python
from nuropb_rmq import ConnectionConfig

cfg = ConnectionConfig(
    host="b-xxxx.mq.us-east-1.amazonaws.com",  # dial target
    port=5671,                                 # AMQPS (provider port may differ)
    virtual_host="/",                          # or your named vhost
    username="app-user",
    password="…",
    tls=True,
    tls_profile="tls-verify-full",
    server_hostname="b-xxxx.mq.us-east-1.amazonaws.com",  # cert DNS / SAN
)
```

Checklist:

- [ ] `tls=True`
- [ ] AMQPS port (usually **5671**)
- [ ] Profile **`tls-verify-full`**
- [ ] Dedicated app user — **not** remote `guest`
- [ ] Correct vhost and permissions ([broker permissions](broker-permissions.md))

## `host` vs `server_hostname`

| Field | Use |
|-------|-----|
| `host` | Where TCP connects (LB VIP, private IP, cluster entry) |
| `server_hostname` | Name for SNI + certificate hostname verification |

If you dial an IP or internal alias but the broker certificate is issued for a
public DNS name, set `server_hostname` to that DNS name. Mismatch is the most
common cloud TLS failure.

## Trust store

| Scenario | Approach |
|----------|----------|
| Public CA (many SaaS brokers) | Often omit `ca_file` and rely on the system trust store (OS/Python) |
| Private / enterprise CA | Set `ca_file` or `ca_data` to your issuing CA (or chain) |
| Amazon MQ / similar | Use the provider’s documented CA / Amazon Root CA as required |

Do not use `tls-insecure-dev-only` in production.

## Auth modes

1. **PLAIN over TLS** — username/password after a verified TLS session (most
   managed brokers).
2. **mTLS + EXTERNAL** — only when the broker advertises `EXTERNAL` **and** you
   configure a client certificate. Never assume mTLS alone disables passwords.

Material options: PEM files, PKCS#12 (`[pkcs12]` extra), or `tls_secrets` hook
for Vault / cloud secret managers. See
[TLS profiles and material](../concepts/tls-profiles-and-material.md).

```python
from nuropb_rmq import ConnectionConfig, TlsMaterial

async def from_secrets_manager() -> TlsMaterial:
    # integrator-owned: fetch and return PEMs
    return TlsMaterial(ca_pem=..., cert_pem=..., key_pem=...)

cfg = ConnectionConfig(
    host="rmq.internal",
    port=5671,
    tls=True,
    tls_secrets=from_secrets_manager,
    server_hostname="rmq.example.com",
    username="app-user",
    password="…",  # still needed unless EXTERNAL is negotiated
)
```

## Provider-agnostic runbook

Works for Amazon MQ for RabbitMQ, CloudAMQP, Azure / AKS-hosted brokers,
and self-managed enterprise clusters:

1. Create a TLS listener (AMQPS) and note host + port.
2. Create least-privilege users and vhosts; disable remote `guest`.
3. Apply **mesh-bind-namespaced** and **reply-publish-restricted** shapes
   ([broker permissions](broker-permissions.md)).
4. Confirm the server certificate DNS/SAN matches what clients put in
   `server_hostname`.
5. Smoke from a jump host: small `AmqpConnection` connect + declare, then your
   mesh example.
6. Prefer secret rotation via `tls_secrets` + reconnect rather than long-lived
   key files on disk when policy requires it.

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Certificate verify failed / hostname mismatch | `server_hostname` ≠ cert SAN; or wrong CA |
| Handshake OK then ACCESS_REFUSED | User/vhost/permissions; guest blocked remotely |
| PLAIN rejected | Broker expects EXTERNAL only, or wrong credentials |
| EXTERNAL not selected | Broker did not advertise it, or no client cert configured |
| Timeouts | Security group / firewall; wrong port; SNI issues behind LB |

## Related

- [Local AMQPS harness](amqps-local.md) — generate certs and smoke on 5671
- [Connection config](../concepts/connection-config.md)
- [Architecture — AMQPS connect](../concepts/architecture-overview.md#amqps-connect)
