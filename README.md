# nuropb-rmq

Native Python RabbitMQ/AMQP 0-9-1 client (no `pika` at runtime). Licensed under
[Apache License 2.0](LICENSE). Design docs live in [`thinking/`](thinking/).
SpeC++ CheckSat lives in [`specs/specpp/`](specs/specpp/); Lean proofs live in
[`specs/lean/`](specs/lean/).

## Status

- Transport + Protocol + Session/RPC + events + mesh + claims
- Reconnect: fail-fast `CONNECTION_LOST`; `Session.reconnect` / `MeshService.rebind`
  (no in-flight park-and-retry)
- Lean Phase 1, 1b, Phase 2, and Pattern (mesh + claims) proved
- SpeC++ Protocol / Session / Pattern / Phase 2 CheckSat
- Throughput harness vs pika under [`bench/`](bench/) (optional `[bench]` extra)
- CI: SpeC++ + unit + claims + RabbitMQ integration + Lean (`lake build`)

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python specs/specpp/check_sat.py
cd specs/lean && lake build && cd ../..
pytest -q
```

## CI / gates

GitHub Actions (`.github/workflows/ci.yml`) runs the same gates:

```bash
ruff check src tests
python specs/specpp/check_sat.py
pytest -q -m "not integration and not benchmark"
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

## Throughput vs pika

```bash
pip install -e ".[bench]"
python -m bench.compare --quick
```
