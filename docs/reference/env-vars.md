# Environment variables

`nuropb-rmq` does **not** load these automatically. Examples, smoke scripts,
and opt-in integration tests read them and build a `ConnectionConfig`.

## Common (examples / smoke)

| Variable | Purpose | Typical default |
|----------|---------|-----------------|
| `NUROPB_RMQ_HOST` | Broker host | `127.0.0.1` |
| `NUROPB_RMQ_PORT` | Broker port | `5672` (smoke may probe `5673`) |
| `NUROPB_RMQ_USER` | Username | `guest` |
| `NUROPB_RMQ_PASSWORD` | Password | `guest` |

Used by `examples/*/`, `scripts/smoke_examples.sh`, and many
`tests/integration/*` modules.

## Topic example

| Variable | Purpose |
|----------|---------|
| `NUROPB_RMQ_BINDING_KEY` | Override binding key for `examples/vanilla_topic/subscriber.py` (default `logs.*`) |

## LangChain example

Owned by [`examples/langchain_example/`](../../examples/langchain_example/) only
(loaded from `.env` / process env by that example — **not** by the core library):

| Variable | Purpose |
|----------|---------|
| `NUROPB_LLM_PROVIDER` | `openai` / `claude` / `grok` (example default: `claude`) |
| `NUROPB_LLM_MODEL` | Optional model override |
| `ANTHROPIC_API_KEY` | Claude |
| `OPENAI_API_KEY` | OpenAI |
| `XAI_API_KEY` | Grok (xAI OpenAI-compatible API) |

See [`.env.example`](../../examples/langchain_example/.env.example) and the
[example README](../../examples/langchain_example/README.md). Live agent needs a
provider key; `--smoke` does not.

## Opt-in AMQPS tests

| Variable | Purpose |
|----------|---------|
| `NUROPB_RMQ_TLS` | Set `1` / `true` / `yes` to run `test_amqps_smoke.py` |
| `NUROPB_RMQ_MTLS` | Set `1` / `true` / `yes` to run `test_amqps_mtls_smoke.py` |
| `NUROPB_RMQ_CA_FILE` | CA PEM path |
| `NUROPB_RMQ_CERT_FILE` | Client cert PEM (mTLS) |
| `NUROPB_RMQ_KEY_FILE` | Client key PEM (mTLS) |
| `NUROPB_RMQ_SERVER_HOSTNAME` | TLS hostname / SNI (often `localhost` for local harness) |

See [Local AMQPS harness](../guides/amqps-local.md).

## Related

- [Connection config](../concepts/connection-config.md)
- [ConnectionConfig fields](connection-config.md)
