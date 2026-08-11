# ConnectionConfig reference

Public import: `from nuropb_rmq import ConnectionConfig, TlsProfile`.

Source: `src/nuropb_rmq/transport/connection.py`.

## Fields

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `host` | `str` | `"127.0.0.1"` | TCP dial target |
| `port` | `int` | `5672` | Use `5671` for AMQPS |
| `virtual_host` | `str` | `"/"` | Broker vhost |
| `username` | `str` | `"guest"` | SASL PLAIN user |
| `password` | `str` | `"guest"` | Redacted in `repr` |
| `heartbeat` | `int` | `60` | Seconds; peer missed at 2× |
| `frame_max` | `int` | library default | Negotiated with broker |
| `tls` | `bool` | `False` | Enable TLS |
| `tls_profile` | `str` | `tls-verify-full` | See `TlsProfile` |
| `ca_file` | `str \| None` | `None` | CA path |
| `cert_file` | `str \| None` | `None` | Client cert path |
| `key_file` | `str \| None` | `None` | Client key path |
| `ca_data` | `bytes \| str \| None` | `None` | In-memory CA PEM |
| `cert_data` | `bytes \| str \| None` | `None` | In-memory client cert PEM |
| `key_data` | `bytes \| str \| None` | `None` | In-memory client key PEM |
| `tls_secrets` | callable / provider \| `None` | `None` | Re-invoked each `connect()` |
| `pkcs12_file` | `str \| None` | `None` | Needs `[pkcs12]` extra |
| `pkcs12_data` | `bytes \| None` | `None` | Needs `[pkcs12]` extra |
| `pkcs12_password` | `bytes \| str \| None` | `None` | Redacted in `repr` |
| `server_hostname` | `str \| None` | `None` | SNI / hostname verify; falls back to `host` |
| `custom_sans` | `list[str]` | `[]` | For `tls-verify-custom-san` |

## TlsProfile values

| Constant | String |
|----------|--------|
| `TlsProfile.VERIFY_FULL` | `tls-verify-full` |
| `TlsProfile.VERIFY_CUSTOM_SAN` | `tls-verify-custom-san` |
| `TlsProfile.INSECURE_DEV_ONLY` | `tls-insecure-dev-only` |

## Related

- [Connection config concept](../concepts/connection-config.md)
- [TLS profiles and material](../concepts/tls-profiles-and-material.md)
