# nuropb-rmq

Native Python RabbitMQ/AMQP 0-9-1 client (no `pika` at runtime). Licensed under
[Apache License 2.0](LICENSE). Design docs live in [`thinking/`](thinking/).
SpeC++ CheckSat lives in [`specs/specpp/`](specs/specpp/); Lean proofs live in
[`specs/lean/`](specs/lean/).

## Status

- Transport + Protocol + Session/RPC + events + mesh + claims
- Reconnect: fail-fast `CONNECTION_LOST`; `Session.reconnect` / `MeshService.rebind`
  (no in-flight park-and-retry)
- Named queue profiles (`durable-at-least-once` default) + heartbeat watchdog
- Lean Phase 1, 1b, Phase 2, and Pattern (mesh + claims) proved
- SpeC++ Protocol / Session / Pattern / Phase 2 / Config CheckSat
- Throughput harness vs pika under [`bench/`](bench/) (optional `[bench]` extra)
- CI: SpeC++ + unit + claims + frame fuzz + RabbitMQ integration + Lean (`lake build`)
- AMQPS: `tls-verify-full` smoke + mTLS/`EXTERNAL` opt-in harness
- Public imports: `from nuropb_rmq import Session, RpcClient, ...` (see `api.py`)

See [`CHANGELOG.md`](CHANGELOG.md) for the **0.1.0** release notes and GitHub
tag checklist (PyPI publish is not automated).

## Branching

Long-lived branches: **`development`** (integration) and **`main`** (stable/release).
Both are protected: changes land via pull request with required CI.

```text
feature/<name>  →  development  →  main
```

1. Update and branch from `development`:

```bash
git checkout development && git pull
git checkout -b feature/my-change
```

2. Open a PR targeting **`development`** (squash merge preferred).
3. When `development` is ready to release, open a PR **`development` → `main`**
   (merge commit preferred so the integration boundary is visible).

Do not push directly to `main` or `development`.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python specs/specpp/check_sat.py
cd specs/lean && lake build && cd ../..
pytest -q
```

CI and the commands above use **pip**. Optional local `uv run …` is fine;
`uv.lock` is gitignored and not the supported CI lockfile.

## CI / gates

GitHub Actions (`.github/workflows/ci.yml`) runs the same gates:

```bash
ruff check src tests
python specs/specpp/check_sat.py
pytest -q -m "not integration and not benchmark and not fuzz"
HYPOTHESIS_PROFILE=ci pytest -q -m fuzz
pip install -e ".[claims]" && pytest -q tests/patterns/test_context.py
# with RabbitMQ on 5672:
pytest -q -m integration
(cd specs/lean && lake build)
```

Claims-gated RPC tests:

```bash
pip install -e ".[claims]"
pytest -q tests/patterns/test_context.py tests/integration/test_mesh_claims_amqp.py
```

Integration smoke (needs RabbitMQ; tries `5672` then `5673`, or set
`NUROPB_RMQ_HOST` / `NUROPB_RMQ_PORT`):

```bash
pytest -q -m integration
```

## AMQPS (tls-verify-full)

Local PLAIN-over-TLS smoke against a broker SSL listener on **5671**:

```bash
./scripts/gen_amqps_certs.sh
# Point RabbitMQ at dev/amqps/{ca,server}.pem + server.key
# (see scripts/rabbitmq-amqps.conf.example), then restart the broker.

export NUROPB_RMQ_TLS=1
export NUROPB_RMQ_HOST=127.0.0.1
export NUROPB_RMQ_PORT=5671
export NUROPB_RMQ_CA_FILE="$PWD/dev/amqps/ca.pem"
export NUROPB_RMQ_SERVER_HOSTNAME=localhost
pytest -q tests/integration/test_amqps_smoke.py
```

Client uses profile **`tls-verify-full`** (chain + hostname). Broker
`ssl_options.verify = verify_none` only means the broker does not require a
client certificate. Private keys under `dev/amqps/` are gitignored.

### mTLS + SASL EXTERNAL

Same cert script also emits `client.pem` / `client.key` (CN `nuropb-client`).
Point the broker at [`scripts/rabbitmq-amqps-mtls.conf.example`](scripts/rabbitmq-amqps-mtls.conf.example)
(`verify_peer`, `fail_if_no_peer_cert`, `EXTERNAL`), then:

```bash
rabbitmq-plugins enable rabbitmq_auth_mechanism_ssl
rabbitmqctl add_user nuropb-client unused-password || true
rabbitmqctl set_permissions -p / nuropb-client ".*" ".*" ".*"
# restart broker with mTLS conf

export NUROPB_RMQ_MTLS=1
export NUROPB_RMQ_HOST=127.0.0.1
export NUROPB_RMQ_PORT=5671
export NUROPB_RMQ_CA_FILE="$PWD/dev/amqps/ca.pem"
export NUROPB_RMQ_CERT_FILE="$PWD/dev/amqps/client.pem"
export NUROPB_RMQ_KEY_FILE="$PWD/dev/amqps/client.key"
export NUROPB_RMQ_SERVER_HOSTNAME=localhost
pytest -q tests/integration/test_amqps_mtls_smoke.py
```

The client prefers `EXTERNAL` only when the broker advertises it **and** a
client cert is configured — never assumes mTLS ⇒ passwordless.

### TLS material sources

CA / client cert / key can come from any of:

| Source | Config |
|--------|--------|
| File paths | `ca_file`, `cert_file`, `key_file` |
| In-memory PEM | `ca_data`, `cert_data`, `key_data` (`bytes` or `str`) |
| Secrets hook | `tls_secrets` — async `SecretsProvider.get_tls_material()` or sync/async callable returning `TlsMaterial` |

One source per slot (file **or** bytes; hook conflicts if the same slot is also set).
The hook is re-invoked on every new `connect()` (rotation via reconnect). PEM only;
PKCS#12 is deferred. `repr` never includes private key PEM or the password.

```python
from nuropb_rmq.transport.connection import ConnectionConfig
from nuropb_rmq.transport.tls_material import TlsMaterial

async def load_from_vault() -> TlsMaterial:
    # integrator-owned: Vault / AWS SM / etc.
    return TlsMaterial(ca_pem=..., cert_pem=..., key_pem=...)

cfg = ConnectionConfig(tls=True, tls_secrets=load_from_vault, server_hostname="localhost")
```

SSL profile + material resolve + SASL selection are covered without a broker:

```bash
pytest -q tests/transport/test_tls_context.py tests/transport/test_tls_material.py
```

## Reconnect (v1 fail-fast)

On disconnect, outstanding RPCs fail with `CONNECTION_LOST`. Reconnect opens a
new connection epoch and exclusive reply queue; mesh consumers must be rebound
and restarted by the caller (no silent in-flight retry / park-and-retry).

```python
from nuropb_rmq.session import Session, ReconnectCoordinator

await ReconnectCoordinator().reconnect(session)
await mesh.rebind()
server = RpcServer.from_mesh(mesh, handler=handler)
await server.start()
```

## Mesh + claims

Broker permission profile **`mesh-bind-namespaced`**: bind/consume only under
`<service>.*`. JWT claims use optional `pip install -e ".[claims]"`.

Broker permission profile **`reply-publish-restricted`**: only authorized
service identities may publish to `nr.reply.*` (forges otherwise). Ops
checklist: [`scripts/reply-publish-restricted.md`](scripts/reply-publish-restricted.md).

## Queue profiles

Work queues default to **`durable-at-least-once`** (quorum + persistent +
TTL/DLX + `x-delivery-limit`). Publish refuses non-persistent messages on
durable profiles. See `nuropb_rmq.config.QueueProfile`.

```python
from nuropb_rmq import RpcServer, durable_classic

server = RpcServer(cfg, queue="orders", handler=handler, queue_profile=durable_classic())
```

Exclusive Session reply queues stay auto-delete/ephemeral (not the work-queue profile).

## Throughput vs pika

```bash
pip install -e ".[bench]"
python -m bench.compare --quick
```
