# nuropb-rmq

[![CI](https://github.com/RileyBetts/nuropb-rmq/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/RileyBetts/nuropb-rmq/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/nuropb-rmq.svg)](https://pypi.org/project/nuropb-rmq/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/status-stable-green.svg)](CHANGELOG.md)

Async-native Python **AMQP 0-9-1** client for RabbitMQ — built on `asyncio`, with
no `pika` (or other AMQP client) at runtime. It implements connection/channel
framing directly and layers nuropb-inspired **JSON-RPC 2.0** mesh patterns (RPC,
events, service bind, claims) on that transport. Protocol and session behaviour
are backed by SpeC++ CheckSat and Lean proofs, not only tests.

1.0: the public API is frozen. See [`docs/reference/api-stability.md`](docs/reference/api-stability.md)
and [`CHANGELOG.md`](CHANGELOG.md). This is an asyncio RPC/event mesh on RabbitMQ,
not a Celery replacement.

## Features

- Asyncio-first API (`await` connect, publish, consume, RPC)
- Native AMQP transport: connect, channel, declare, publish, consume, ack
- Session RPC with exclusive reply queues and correlation tracking
- Event pub/sub (JSON-RPC notification shape) over topic/fanout
- Mesh service bind under a namespaced identity (`service.method`)
- Optional JWT claims on RPC (`[claims]` extra)
- TLS (`tls-verify-full`), mTLS / SASL `EXTERNAL`, PEM + PKCS#12 + secrets hook
- Named queue profiles (`durable-at-least-once` default) and heartbeat watchdog
- Park-and-retry reconnect (default); fail-fast via `fail_outstanding=True`
- Mandatory publish / `basic.return` (`PublishReturned`) so misrouted RPC is an error
- Optional mesh discovery registry (announce/viewer — never a bind authority)
- Runnable LangChain tool + LangGraph remote-node examples over the mesh
- Throughput harness vs pika (`[bench]` extra)

## Installation

Python 3.11+:

```bash
pip install nuropb-rmq
```

| Extra | Purpose |
|-------|---------|
| *(none)* | Core client |
| `claims` | JWT mesh claims (`PyJWT`) |
| `pkcs12` | PKCS#12 TLS material (`cryptography`) |
| `bench` | pika comparison harness |

```bash
pip install "nuropb-rmq[claims]"
```

From a known Git tag (or before a version is on PyPI):

```bash
pip install "git+https://github.com/RileyBetts/nuropb-rmq.git@v1.0.0"
```

Pushing an annotated `v*` tag from `main` publishes to PyPI via
[`.github/workflows/publish.yml`](.github/workflows/publish.yml). Release checklist:
[`CHANGELOG.md`](CHANGELOG.md).

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

**Transport**

- [`examples/vanilla_hello/`](examples/vanilla_hello/) — durable queue publish/consume
- [`examples/vanilla_topic/`](examples/vanilla_topic/) — topic exchange pub/sub

**Mesh**

- [`examples/one_client_one_service/`](examples/one_client_one_service/) — mesh RPC,
  events, and registry discovery

**Framework adapters** (self-standing `uv` projects — LangChain/LangGraph deps stay
out of the root package)

- [`examples/langchain_example/`](examples/langchain_example/) — LangChain agent calling
  a mesh service tool (`orders.get_status`); live agent needs an LLM key,
  `--smoke` does not
- [`examples/langgraph_example/`](examples/langgraph_example/) — LangGraph remote
  invoice extract over mesh RPC; optional `reconnect_demo.py` for
  `CONNECTION_LOST` → rebind → checkpoint replay

Smoke examples (with [uv](https://docs.astral.sh/uv/) after `uv sync --dev`;
also `uv sync` in `examples/langchain_example` and `examples/langgraph_example`):

```bash
./scripts/smoke_examples.sh
```

## Documentation

User guides (config, AMQPS, mesh, claims): **[`docs/`](docs/README.md)**

- [Architecture overview](docs/concepts/architecture-overview.md) — diagrams
- [Service mesh](docs/concepts/service-mesh.md) — what “mesh” means here
- [JWT claims](docs/concepts/jwt-claims.md)
- [Cloud and enterprise AMQPS](docs/guides/cloud-and-enterprise-amqps.md)
- [TLS profiles and material](docs/concepts/tls-profiles-and-material.md)
- [Broker permissions](docs/guides/broker-permissions.md)

Lean ↔ Python map: [`specs/lean/CORRESPONDENCE.md`](specs/lean/CORRESPONDENCE.md).
Release notes: [`CHANGELOG.md`](CHANGELOG.md).

## Formal verification

Correctness work is part of the project, not an afterthought:

- SpeC++ SMT CheckSat under [`specs/specpp/`](specs/specpp/) (Protocol, Session,
  Pattern, Phase 2, Config)
- Lean proofs under [`specs/lean/`](specs/lean/) (Protocol, Session, Pattern,
  Config, reconnect)

Contributor commands to run these gates are in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## TLS, mesh, reconnect (summary)

- Prefer **`tls-verify-full`**; never assume mTLS ⇒ `EXTERNAL`. Full material
  sources and cloud runbooks: [`docs/guides/cloud-and-enterprise-amqps.md`](docs/guides/cloud-and-enterprise-amqps.md).
- Mesh is JSON-RPC over RabbitMQ (not a sidecar mesh):
  [`docs/concepts/service-mesh.md`](docs/concepts/service-mesh.md).
- Reconnect **parks** in-flight client RPCs by default (at-least-once republish);
  fail-fast is `fail_outstanding=True`; caller still rebinds mesh servers:
  [`docs/concepts/reconnect.md`](docs/concepts/reconnect.md).
- LangGraph / long-running clients: retry authority is application-owned —
  [`docs/guides/langgraph.md`](docs/guides/langgraph.md).
- Work queues default to `durable-at-least-once`:
  [`docs/concepts/queue-profiles.md`](docs/concepts/queue-profiles.md).

```python
from nuropb_rmq import MeshRegistryViewer, MeshService, ServiceIdentity

mesh = MeshService(cfg, identity=ServiceIdentity("orders"), methods=["ping"], announce=True)
await mesh.start()
```

## Throughput vs pika

On a 2026-09-01 laptop run (Docker RabbitMQ 3.13.7, no TLS), **raw
publish/consume and fanout** were about **2×–3×** blocking pika at small and
medium bodies, and roughly tied at 16 KiB. **JSON-RPC on an exclusive reply
queue** (the mesh path) is slower than pika’s thinner blocking RPC — plan on
the order of **100–700 round trips per second per process**, depending on
parallelism, not thousands. Details, caveats, and how to re-run:
[`docs/concepts/performance.md`](docs/concepts/performance.md).

```bash
uv sync --dev --extra bench
uv run python -m bench.compare --quick
```

## Contributing

PRs target **`development`**. **`main` and `development` are protected** — no
direct commits. Branch from `development` as `feature/<name>`. Use
[uv](https://docs.astral.sh/uv/) for the maintainer environment
(`uv sync --dev`). Branching, CI gates, SpeC++, and Lean commands:
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[Apache License 2.0](LICENSE)
