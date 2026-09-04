# nuropb-rmq

[![CI](https://github.com/RileyBetts/nuropb-rmq/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/RileyBetts/nuropb-rmq/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/nuropb-rmq.svg)](https://pypi.org/project/nuropb-rmq/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Lean](https://img.shields.io/badge/lean-4.33-purple.svg)](https://lean-lang.org/)
[![Status](https://img.shields.io/badge/status-stable-green.svg)](CHANGELOG.md)

Two packages, one RabbitMQ mesh. **Python** (`nuropb-rmq` / `nuropb_rmq`) and
**Lean 4** (`NuropbRMQ`) are separate runtimes on the same SpeC++ / Lean
kernels. There is no extraction either way: the PyPI wheel does not embed Lean
FFI, and Lean apps do not load Python.

Both speak **AMQP 0-9-1** and nuropb-inspired **JSON-RPC 2.0** patterns (RPC,
events, service bind, claims). Protocol and session behaviour are backed by
SpeC++ CheckSat and Lean proofs, not only tests.

Python 1.0 (`from nuropb_rmq import …`) is frozen. Lean names mirror that API
and are not a Python API change. See
[`docs/reference/api-stability.md`](docs/reference/api-stability.md) and
[`specs/lean/CORRESPONDENCE.md`](specs/lean/CORRESPONDENCE.md). This is an
RPC/event mesh on RabbitMQ, not a Celery replacement.

## Two packages

| | Python | Lean |
|---|---|---|
| Package | PyPI **`nuropb-rmq`** | Lake / Reservoir **`NuropbRMQ`** (repo root) |
| Import | `import nuropb_rmq` / `from nuropb_rmq import …` | `import NuropbRMQ` |
| Runtime | asyncio, no `pika` | POSIX sockets (`lake build NuropbRMQ`) |
| Proofs | consumes the same kernels via tests | `lake build NuropbRMQSpec` (`import NuropbRmq.*`, no IO) |
| TLS | `tls-verify-full`; mTLS / `EXTERNAL`; PEM + PKCS#12 | default build is libc; AMQPS / mTLS / RS256/ES256 on `NuropbRMQTls` |
| Freeze | 1.0 public names in [`api.py`](src/nuropb_rmq/api.py) | second runtime; not a Python 1.x bump |

They interoperate on the broker: Lean publisher ↔ Python consumer, Lean mesh
client ↔ Python service, and the reverse. Map: [CORRESPONDENCE Runtime](specs/lean/CORRESPONDENCE.md).

## Features

Shared mesh behaviour (both packages unless noted):

- Native AMQP transport: connect, channel, declare, publish, consume, ack
- Session RPC with exclusive reply queues and correlation tracking
- Event pub/sub (JSON-RPC notification shape) over topic/fanout
- Mesh service bind under a namespaced identity (`service.method`)
- Optional JWT claims on RPC (Python `[claims]` extra; Lean HS256 in-tree,
  RS256/ES256 on `NuropbRMQTls`)
- TLS (`tls-verify-full`), mTLS / SASL `EXTERNAL`, PEM + PKCS#12
- Named queue profiles (`durable-at-least-once` default) and heartbeat watchdog
- Park-and-retry reconnect (default); fail-fast via `fail_outstanding=True`
- Optional process-local request-id dedup (`dedup_window` / Lean `tryDedup`)
- Mandatory publish / `basic.return` so misrouted RPC is an error
- Optional mesh discovery registry (announce/viewer — never a bind authority)

Python-only: asyncio API; throughput harness vs pika (`[bench]`); LangChain /
LangGraph adapters stay in `examples/` (not a core extra, not in Lean).

## Installation

### Python (PyPI)

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
[`.github/workflows/publish.yml`](.github/workflows/publish.yml).

### Lean (Lake)

Lean 4.33. The Lake package is **`NuropbRMQ`** at the repository root
(`lake-manifest.json`). Proofs are target **`NuropbRMQSpec`**.

```text
require NuropbRMQ from git "https://github.com/RileyBetts/nuropb-rmq" @ "<tag>"
```

```bash
# from this repo root — not cd specs/lean
lake build NuropbRMQSpec   # kernels + proofs (no sockets)
lake build NuropbRMQ       # POSIX AMQP / mesh client
lake build NuropbRMQTls    # optional OpenSSL AMQPS / mTLS / RS+ES JWT
```

Then `import NuropbRMQ`. Default `lake build` does not link OpenSSL.
Details: [`specs/lean/README.md`](specs/lean/README.md).

## Quick start

Needs a local RabbitMQ broker (default `127.0.0.1:5672`, `guest`/`guest`).

### Python

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

Stable imports: `from nuropb_rmq import Session, RpcClient, MeshService, …`
([`api.py`](src/nuropb_rmq/api.py)).

### Lean

```lean
import NuropbRMQ

def main : IO Unit := do
  let c ← NuropbRMQ.connect {}
  let _ ← NuropbRMQ.openChannel c 1
  let q ← NuropbRMQ.queueDeclare c 1 "nr.ex.hello" (durable := true)
  NuropbRMQ.basicPublish c 1 "hello-nuropb-rmq".toUTF8 "" q
    { deliveryMode := some 2, contentType := some "text/plain" }
    (wantConfirm := true)
  NuropbRMQ.close c
```

`connect {}` uses `127.0.0.1:5672` / `guest`. For `NUROPB_RMQ_*`, pass
`(← NuropbRMQ.envConfig)`. Copy-paste trees: **Examples** below.

## Examples

**Python transport / mesh**

- [`examples/vanilla_hello/`](examples/vanilla_hello/) — durable queue publish/consume
- [`examples/vanilla_topic/`](examples/vanilla_topic/) — topic exchange pub/sub
- [`examples/one_client_one_service/`](examples/one_client_one_service/) — mesh RPC,
  events, and registry discovery

**Lean** (`lake exe lean_*`; same broker)

- [`examples/LeanHello/`](examples/LeanHello/) — durable publish/consume
- [`examples/LeanMesh/`](examples/LeanMesh/) — mesh service + client
- [`examples/LeanClaims/`](examples/LeanClaims/) — HS256 + `authorize` deny/allow
- Coverage smokes (events, DLQ, park reconnect, dedup): `./scripts/smoke_lean_coverage.sh`

**Interop** (Lean ↔ Python on one broker)

- [`examples/interop_hello/`](examples/interop_hello/)
- [`examples/interop_mesh/`](examples/interop_mesh/)

**Framework adapters** (Python-only; LangChain/LangGraph stay out of both
core packages)

- [`examples/langchain_example/`](examples/langchain_example/)
- [`examples/langgraph_example/`](examples/langgraph_example/)

```bash
./scripts/smoke_examples.sh
./scripts/smoke_interop.sh          # Lean ↔ Python; needs lake
./scripts/smoke_lean_coverage.sh    # Lean IO coverage
./scripts/smoke_lean_amqps.sh       # optional NuropbRMQTls
./scripts/smoke_lean_mtls.sh        # mTLS + SASL EXTERNAL
```

## Documentation

User guides (config, AMQPS, mesh, claims): **[`docs/`](docs/README.md)**.
What's next vs residual: [`docs/ROADMAP.md`](docs/ROADMAP.md).

- [Architecture overview](docs/concepts/architecture-overview.md) — two runtimes
- [Service mesh](docs/concepts/service-mesh.md)
- [JWT claims](docs/concepts/jwt-claims.md)
- [Cloud and enterprise AMQPS](docs/guides/cloud-and-enterprise-amqps.md)
- [TLS profiles and material](docs/concepts/tls-profiles-and-material.md)
- [Broker permissions](docs/guides/broker-permissions.md)
- [Reconnect](docs/concepts/reconnect.md) — park-and-retry; optional `dedup_window`

## Formal verification

- SpeC++ SMT CheckSat: [`specs/specpp/`](specs/specpp/)
- Lean proofs: [`specs/lean/`](specs/lean/) — `lake build NuropbRMQSpec`
- Lean IO client: `import NuropbRMQ` (imports those kernels; no extraction)
- Lean ↔ Python map: [`specs/lean/CORRESPONDENCE.md`](specs/lean/CORRESPONDENCE.md)

Contributor gates: [`CONTRIBUTING.md`](CONTRIBUTING.md).

## TLS, mesh, reconnect (summary)

- Prefer **`tls-verify-full`**; never assume mTLS ⇒ `EXTERNAL`.
  [`docs/guides/cloud-and-enterprise-amqps.md`](docs/guides/cloud-and-enterprise-amqps.md)
- Mesh is JSON-RPC over RabbitMQ (not a sidecar mesh):
  [`docs/concepts/service-mesh.md`](docs/concepts/service-mesh.md)
- Reconnect **parks** in-flight client RPCs by default (at-least-once delivery);
  fail-fast is `fail_outstanding=True`; optional `dedup_window` is handler-once
  in-process: [`docs/concepts/reconnect.md`](docs/concepts/reconnect.md)
- LangGraph / long-running clients: retry authority is application-owned —
  [`docs/guides/langgraph.md`](docs/guides/langgraph.md) (Python examples only)
- Work queues default to `durable-at-least-once`:
  [`docs/concepts/queue-profiles.md`](docs/concepts/queue-profiles.md)

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
parallelism, not thousands. Details:
[`docs/concepts/performance.md`](docs/concepts/performance.md).

```bash
uv sync --dev --extra bench
uv run python -m bench.compare --quick
```

## Contributing

PRs target **`development`**. **`main` and `development` are protected** — no
direct commits. Branch from `development` as `feature/<name>`. Use
[uv](https://docs.astral.sh/uv/) for the Python maintainer environment
(`uv sync --dev`) and Lake for Lean. Branching, CI, SpeC++, and Lean commands:
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[Apache License 2.0](LICENSE)
