# nuropb-rmq

Native Python RabbitMQ/AMQP 0-9-1 client (no `pika` at runtime). Design docs
live in [`thinking/`](thinking/). SpeC++ CheckSat lives in
[`specs/specpp/`](specs/specpp/); Lean proofs live in [`specs/lean/`](specs/lean/).

## Status

- Transport + Protocol: connect, channel, declare, publish/consume/ack
- Session + JSON-RPC RPC (exclusive reply queue, DLQ timeout path)
- Events/pub-sub: JSON-RPC notifications over topic/fanout
- Lean Phase 1 + Phase 1b (Protocol SM + Session correlation) proved
- Throughput harness vs pika under [`bench/`](bench/) (optional `[bench]` extra)
- Mesh / claims not implemented yet

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

Covers raw AMQP, RPC request/reply + DLQ timeout, and event fanout/topic.

Formal gates:

```bash
python specs/specpp/check_sat.py   # SpeC++ Protocol + Session SMT
(cd specs/lean && lake build)      # Lean Phase 1 + Phase 1b proofs
```

## Throughput vs pika

`pika` is **only** for development/test performance comparisons — never a
runtime dependency of `nuropb_rmq`.

```bash
pip install -e ".[bench]"
python -m bench.compare --quick          # small matrix
python -m bench.compare                  # full matrix (sizes 64/1k/16k, conc 1/8)
pytest -q -m benchmark                   # small-count harness smoke
```

Reports land in `bench/results/*.json` with msgs/sec and latency p50/p99.
Scenarios: raw publish/consume, RPC exclusive reply queue, pika
`amq.rabbitmq.reply-to`, and fanout events.
