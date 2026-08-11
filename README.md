# nuropb-rmq

[![CI](https://github.com/RileyBetts/nuropb-rmq/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/RileyBetts/nuropb-rmq/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](CHANGELOG.md)

Async-native Python **AMQP 0-9-1** client for RabbitMQ — built on `asyncio`, with
no `pika` (or other AMQP client) at runtime. It implements connection/channel
framing directly and layers nuropb-inspired **JSON-RPC 2.0** mesh patterns (RPC,
events, service bind, claims) on that transport. Protocol and session behaviour
are backed by SpeC++ CheckSat and Lean proofs, not only tests.

Alpha: the public API may still change. See [`CHANGELOG.md`](CHANGELOG.md).

## Features

- Asyncio-first API (`await` connect, publish, consume, RPC)
- Native AMQP transport: connect, channel, declare, publish, consume, ack
- Session RPC with exclusive reply queues and correlation tracking
- Event pub/sub (JSON-RPC notification shape) over topic/fanout
- Mesh service bind under a namespaced identity (`service.method`)
- Optional JWT claims on RPC (`[claims]` extra)
- TLS (`tls-verify-full`), mTLS / SASL `EXTERNAL`, PEM + PKCS#12 + secrets hook
- Named queue profiles (`durable-at-least-once` default) and heartbeat watchdog
- Fail-fast reconnect (`CONNECTION_LOST`); caller rebinds mesh consumers
- Optional mesh discovery registry (announce/viewer — never a bind authority)
- Throughput harness vs pika (`[bench]` extra)

## Installation

Python 3.11+. Until PyPI publish is wired up, install from GitHub:

```bash
pip install "git+https://github.com/RileyBetts/nuropb-rmq.git"
```

| Extra | Purpose |
|-------|---------|
| *(none)* | Core client |
| `claims` | JWT mesh claims (`PyJWT`) |
| `pkcs12` | PKCS#12 TLS material (`cryptography`) |
| `bench` | pika comparison harness |

```bash
pip install "nuropb-rmq[claims] @ git+https://github.com/RileyBetts/nuropb-rmq.git"
```

PyPI publish is not automated; the 0.1.0 GitHub release checklist lives in the
changelog.

## Quick start

Needs a local RabbitMQ broker (default `127.0.0.1:5672`, `guest`/`guest`).

```python
import asyncio
from nuropb_rmq import AmqpConnection, ConnectionConfig

async def main() -> None:
    conn = AmqpConnection(ConnectionConfig(host="127.0.0.1", port=5672))
    await conn.connect()
    ch = await conn.open_channel(1)
    queue = await conn.queue_declare(ch, "nr.ex.hello", durable=True)
    await conn.basic_consume(ch, queue)
    await conn.basic_publish(
        ch,
        b"hello-nuropb-rmq",
        routing_key=queue,
        properties={"content_type": "text/plain", "delivery_mode": 2},
    )
    msg = await conn.receive(timeout=5)
    print(msg.body)
    await conn.basic_ack(ch, msg.delivery_tag)
    await conn.close()

asyncio.run(main())
```

Prefer copy-paste demos? See **Examples** below. Stable imports:
`from nuropb_rmq import Session, RpcClient, MeshService, …` ([`api.py`](src/nuropb_rmq/api.py)).

## Examples

- [`examples/vanilla_hello/`](examples/vanilla_hello/) — durable queue publish/consume
- [`examples/vanilla_topic/`](examples/vanilla_topic/) — topic exchange pub/sub
- [`examples/one_client_one_service/`](examples/one_client_one_service/) — mesh RPC,
  events, and registry discovery

Smoke all three (with [uv](https://docs.astral.sh/uv/) after `uv sync --dev`):

```bash
./scripts/smoke_examples.sh
```

## Documentation

- Design: [`thinking/architecture.md`](thinking/architecture.md)
- Lean ↔ Python map: [`specs/lean/CORRESPONDENCE.md`](specs/lean/CORRESPONDENCE.md)
- Reply-queue ops profile: [`scripts/reply-publish-restricted.md`](scripts/reply-publish-restricted.md)
- Release notes: [`CHANGELOG.md`](CHANGELOG.md)

## Formal verification

Correctness work is part of the project, not an afterthought:

- SpeC++ SMT CheckSat under [`specs/specpp/`](specs/specpp/) (Protocol, Session,
  Pattern, Phase 2, Config)
- Lean proofs under [`specs/lean/`](specs/lean/) (Protocol, Session, Pattern,
  Config, reconnect)

Contributor commands to run these gates are in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## TLS and security

- Profiles: **`tls-verify-full`** (chain + hostname). Never assume mTLS ⇒
  passwordless; `EXTERNAL` is used only when the broker advertises it **and** a
  client cert is configured.
- Local AMQPS / mTLS harnesses: [`scripts/gen_amqps_certs.sh`](scripts/gen_amqps_certs.sh),
  [`scripts/rabbitmq-amqps.conf.example`](scripts/rabbitmq-amqps.conf.example),
  [`scripts/rabbitmq-amqps-mtls.conf.example`](scripts/rabbitmq-amqps-mtls.conf.example),
  and opt-in tests under `tests/integration/test_amqps_*.py`.

### TLS material sources

| Source | Config |
|--------|--------|
| File paths | `ca_file`, `cert_file`, `key_file` |
| In-memory PEM | `ca_data`, `cert_data`, `key_data` |
| PKCS#12 | `pkcs12_file` / `pkcs12_data` (+ optional password); `[pkcs12]` extra |
| Secrets hook | `tls_secrets` → `TlsMaterial` (re-run on each `connect()`) |

All sources normalize to PEM `TlsMaterial` before SSLContext construction.
`repr` never includes private key material or passwords.

```python
from nuropb_rmq import ConnectionConfig, TlsMaterial

async def load_from_vault() -> TlsMaterial:
    return TlsMaterial(ca_pem=..., cert_pem=..., key_pem=...)

cfg = ConnectionConfig(tls=True, tls_secrets=load_from_vault, server_hostname="localhost")
```

## Reconnect

On disconnect, outstanding RPCs fail with `CONNECTION_LOST`. Reconnect opens a
new connection epoch and exclusive reply queue; mesh consumers must be rebound
and restarted by the caller (no silent in-flight park-and-retry).

```python
from nuropb_rmq import ReconnectCoordinator, RpcServer

await ReconnectCoordinator().reconnect(session)
await mesh.rebind()
server = RpcServer.from_mesh(mesh, handler=handler)
await server.start()
```

## Mesh and claims

- Broker profile **`mesh-bind-namespaced`**: bind/consume only under `<service>.*`.
- Broker profile **`reply-publish-restricted`**: only authorized services may
  publish to `nr.reply.*` — see
  [`scripts/reply-publish-restricted.md`](scripts/reply-publish-restricted.md).
- JWT claims: `pip install 'nuropb-rmq[claims]'` (or `uv sync --extra claims`).
- Discovery aid: `MeshService(..., announce=True)` + `MeshRegistryViewer` on
  `nr.mesh.registry` — never replaces broker ACL or `assert_bind_allowed`.

```python
from nuropb_rmq import MeshRegistryViewer, MeshService, ServiceIdentity

mesh = MeshService(cfg, identity=ServiceIdentity("orders"), methods=["ping"], announce=True)
await mesh.start()
viewer = MeshRegistryViewer(cfg)
await viewer.start()
print(viewer.lookup("orders"))
```

## Queue profiles

Work queues default to **`durable-at-least-once`** (quorum + persistent + TTL/DLX +
`x-delivery-limit`). Durable profiles refuse non-persistent publishes. Session
reply queues stay exclusive/auto-delete.

```python
from nuropb_rmq import RpcServer, durable_classic

server = RpcServer(cfg, queue="orders", handler=handler, queue_profile=durable_classic())
```

## Throughput vs pika

```bash
uv sync --dev --extra bench
uv run python -m bench.compare --quick
```

## Contributing

PRs target **`development`**. Use [uv](https://docs.astral.sh/uv/) for the
maintainer environment (`uv sync --dev`). Branching, CI gates, SpeC++, and Lean
commands: [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[Apache License 2.0](LICENSE)
