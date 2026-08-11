# Vanilla hello: publish / consume

Uses only `AmqpConnection` — no mesh, Session, or JSON-RPC.

```text
publisher.py  --default exchange-->  nr.ex.hello  -->  consumer.py
```

## Prerequisites

- RabbitMQ (default `127.0.0.1:5672`, `guest` / `guest`)
- From the repo root: `pip install -e .`

Optional: `NUROPB_RMQ_HOST`, `NUROPB_RMQ_PORT`, `NUROPB_RMQ_USER`, `NUROPB_RMQ_PASSWORD`.

## Run

**Terminal 1 — consumer** (durable queue; safe to start either side first):

```bash
python examples/vanilla_hello/consumer.py
```

**Terminal 2 — publisher:**

```bash
python examples/vanilla_hello/publisher.py
python examples/vanilla_hello/publisher.py "another message"
```

Expected:

```text
[publisher] sent b'hello-nuropb-rmq' -> queue='nr.ex.hello'
[consumer] received 'hello-nuropb-rmq' routing_key='nr.ex.hello'
```
