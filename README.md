# nuropb-rmq

Native Python RabbitMQ/AMQP 0-9-1 client (no `pika`). Design docs live in
[`thinking/`](thinking/). SpeC++ CheckSat lives in [`specs/specpp/`](specs/specpp/);
Lean Protocol proofs live in [`specs/lean/`](specs/lean/).

## Status

Transport + Protocol foundation: connect, open a channel, declare a queue,
publish/consume/ack. Lean Phase 1 Protocol SM invariants 1–7 proved.
Session/RPC/mesh patterns are not implemented yet.

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

Formal gates:

```bash
python specs/specpp/check_sat.py   # SpeC++ SMT consistency
(cd specs/lean && lake build)      # Lean Phase 1 Protocol proofs
```
