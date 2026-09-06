# TLS profiles and material

AMQPS is configured entirely through `ConnectionConfig` (`tls=True` plus a
named profile and certificate material).

## Profiles

| Profile | Meaning |
|---------|---------|
| `tls-verify-full` | **Default.** Verify CA chain + hostname (via `server_hostname` or `host`). |
| `tls-verify-custom-san` | Verify chain (stdlib hostname check). Configured
  `server_hostname` / `host` must be in `custom_sans` **before** connect — not
  a custom cert-SAN inspector. |
| `tls-insecure-dev-only` | No verification — local experiments only, never production. |

Named profiles avoid a silent `verify=False` footgun.

## Material sources

All paths normalize to PEM `TlsMaterial` before `SSLContext` construction.

| Source | Config |
|--------|--------|
| File paths | `ca_file`, `cert_file`, `key_file` |
| In-memory PEM | `ca_data`, `cert_data`, `key_data` (`bytes` or `str`) |
| PKCS#12 | `pkcs12_file` or `pkcs12_data` (+ optional `pkcs12_password`); requires `[pkcs12]` extra |
| Secrets hook | `tls_secrets` — async `SecretsProvider.get_tls_material()` or sync/async callable returning `TlsMaterial` |

Rules of thumb:

- One source per slot (file **or** bytes; do not also set the same slot via the hook).
- PKCS#12 is mutually exclusive with PEM `cert_*` / `key_*` (and with a hook that supplies those slots).
- If the PKCS#12 bag includes CA certs, do not also set `ca_*`.
- The secrets hook is **re-invoked on every new `connect()`** (rotation via reconnect).
- `repr(ConnectionConfig)` never includes private key PEM or passwords.

```python
from nuropb_rmq import ConnectionConfig, TlsMaterial

async def load_from_vault() -> TlsMaterial:
    return TlsMaterial(ca_pem=..., cert_pem=..., key_pem=...)

cfg = ConnectionConfig(
    tls=True,
    tls_secrets=load_from_vault,
    server_hostname="rmq.example.com",
)
```

## mTLS and SASL EXTERNAL

Client certificates enable mutual TLS. The client prefers SASL **`EXTERNAL`**
only when:

1. The broker advertises `EXTERNAL`, **and**
2. A client cert is configured (any material source).

Never assume “mTLS is on ⇒ passwordless.” Many brokers still expect PLAIN over
TLS with a username/password.

## Related

- [Cloud and enterprise AMQPS](../guides/cloud-and-enterprise-amqps.md)
- [Local AMQPS harness](../guides/amqps-local.md)
- Unit coverage without a broker: `tests/transport/test_tls_context.py`,
  `tests/transport/test_tls_material.py`
