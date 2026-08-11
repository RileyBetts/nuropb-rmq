# nuropb-rmq

Native Python RabbitMQ/AMQP 0-9-1 client (no `pika`). Design docs live in
[`thinking/`](thinking/). SpeC++ CheckSat lives in [`specs/specpp/`](specs/specpp/);
Lean proofs live in [`specs/lean/`](specs/lean/).

## Status

Transport + Protocol + Session/RPC foundation:

- Connect, channel, declare, publish/consume/ack (no `pika`)
- Lean Phase 1 Protocol SM invariants 1–7 proved
- Session exclusive reply queue + correlation table + JSON-RPC RPC
- Lean Phase 1b Session correlation invariants proved
- Mesh / events / claims not implemented yet

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python specs/specpp/check_sat.py
cd specs/lean && lake build && cd ../..
pytest -q
```

Integration smoke (needs RabbitMQ; tries `5672` then `5673`, or set
`NUROPB_RMQ_HOST` / `NUROPB_RMQ_PORT`):

```bash
pytest -q -m integration
```

RPC smoke covers successful `request`/`result` and DLQ-synthesized
`REQUEST_TIMEOUT` when the service never answers.

Formal gates:

```bash
python specs/specpp/check_sat.py   # SpeC++ Protocol + Session SMT
(cd specs/lean && lake build)      # Lean Phase 1 + Phase 1b proofs
```
