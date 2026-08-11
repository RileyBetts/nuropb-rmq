# nuropb-rmq

Native Python RabbitMQ/AMQP 0-9-1 client (no `pika` at runtime). Design docs
live in [`thinking/`](thinking/). SpeC++ CheckSat lives in
[`specs/specpp/`](specs/specpp/); Lean proofs live in [`specs/lean/`](specs/lean/).

## Status

- Transport + Protocol: connect, channel, declare, publish/consume/ack
- Session + JSON-RPC RPC (exclusive reply queue, DLQ timeout path)
- Events/pub-sub: JSON-RPC notifications over topic/fanout
- Mesh: namespaced `service.method` bind (`MeshService`); broker profile
  `mesh-bind-namespaced` (documented; ACL is deployment-owned)
- Claims: JWT in AMQP headers `nr.claims` / `nr.claims_typ` (optional `[claims]`)
- Lean Phase 1 + Phase 1b proved; SpeC++ Protocol/Session/Pattern CheckSat
- Throughput harness vs pika under [`bench/`](bench/) (optional `[bench]` extra)
- Reconnect / Lean Phase 2 not implemented yet

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python specs/specpp/check_sat.py
cd specs/lean && lake build && cd ../..
pytest -q
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

Covers raw AMQP, RPC + DLQ timeout, events, mesh RPC, and claims fail-closed.

Formal gates:

```bash
python specs/specpp/check_sat.py   # SpeC++ Protocol + Session + Pattern
(cd specs/lean && lake build)      # Lean Phase 1 + Phase 1b proofs
```

## Mesh + claims

Broker permission profile **`mesh-bind-namespaced`**: the AMQP user may only
bind/consume under the service’s `<service>.*` routing keys. The library
refuses out-of-namespace binds client-side; it does not replace broker ACL.

```python
from nuropb_rmq.patterns import MeshService, ServiceIdentity, RpcServer, AuthConfig

mesh = MeshService(identity=ServiceIdentity("orders"), methods=["ping"])
await mesh.start()
server = RpcServer.from_mesh(mesh, handler=handler, auth=AuthConfig(jwt_secret=...))
```

JWT verification needs `pip install -e ".[claims]"` (PyJWT + cryptography).
Tokens travel only in AMQP headers — never in the JSON-RPC body.

## Throughput vs pika

`pika` is **only** for development/test performance comparisons — never a
runtime dependency of `nuropb_rmq`.

```bash
pip install -e ".[bench]"
python -m bench.compare --quick
pytest -q -m benchmark
```
