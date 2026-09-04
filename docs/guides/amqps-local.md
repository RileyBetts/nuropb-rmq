# Local AMQPS harness

Smoke TLS (and optional mTLS) against a local RabbitMQ SSL listener on **5671**.
Production patterns: [Cloud and enterprise AMQPS](cloud-and-enterprise-amqps.md).

## Generate certs

```bash
./scripts/gen_amqps_certs.sh
```

Outputs under `dev/amqps/` (private keys are gitignored): CA, server, and client
material.

## PLAIN over TLS (`tls-verify-full`)

1. Point RabbitMQ at the generated server cert/key and CA using
   [`scripts/rabbitmq-amqps.conf.example`](../../scripts/rabbitmq-amqps.conf.example),
   then restart the broker.
2. Run the opt-in smoke test:

```bash
export NUROPB_RMQ_TLS=1
export NUROPB_RMQ_HOST=127.0.0.1
export NUROPB_RMQ_PORT=5671
export NUROPB_RMQ_CA_FILE="$PWD/dev/amqps/ca.pem"
export NUROPB_RMQ_SERVER_HOSTNAME=localhost
pytest -q tests/integration/test_amqps_smoke.py
```

Broker `ssl_options.verify = verify_none` only means the **broker** does not
require a client certificate. The **client** still uses `tls-verify-full`.

## mTLS + SASL EXTERNAL

1. Use
   [`scripts/rabbitmq-amqps-mtls.conf.example`](../../scripts/rabbitmq-amqps-mtls.conf.example)
   (`verify_peer`, `fail_if_no_peer_cert`, `EXTERNAL`).
2. Enable the SSL auth plugin and map the client CN:

```bash
rabbitmq-plugins enable rabbitmq_auth_mechanism_ssl
rabbitmqctl add_user nuropb-client unused-password || true
rabbitmqctl set_permissions -p / nuropb-client ".*" ".*" ".*"
# restart broker with mTLS conf
```

3. Run Python and/or Lean smokes (Docker starter: `scripts/ci_start_amqps_mtls_broker.sh`):

```bash
export NUROPB_RMQ_MTLS=1
export NUROPB_RMQ_HOST=127.0.0.1
export NUROPB_RMQ_PORT=5671
export NUROPB_RMQ_CA_FILE="$PWD/dev/amqps/ca.pem"
export NUROPB_RMQ_CERT_FILE="$PWD/dev/amqps/client.pem"
export NUROPB_RMQ_KEY_FILE="$PWD/dev/amqps/client.key"
export NUROPB_RMQ_SERVER_HOSTNAME=localhost
pytest -q tests/integration/test_amqps_mtls_smoke.py
./scripts/smoke_lean_mtls.sh
```

The client prefers `EXTERNAL` only when the broker advertises it **and** a
client cert is configured. Lean `selectSasl` matches that rule. Default
`lake build` still does not link OpenSSL (`lake build NuropbRMQTls`).

## Related

- [TLS profiles and material](../concepts/tls-profiles-and-material.md)
- [Environment variables](../reference/env-vars.md)
- SSL unit tests (no broker): `tests/transport/test_tls_context.py`
