# Vanilla topic: pub / sub

Uses only `AmqpConnection` — topic exchange routing, no mesh or EventPublisher.

```text
publisher.py  -->  nr.ex.logs (topic)  --logs.*-->  subscriber.py
```

## Prerequisites

- RabbitMQ (default `127.0.0.1:5672`, `guest` / `guest`)
- From the repo root: `pip install -e .`

Optional: `NUROPB_RMQ_HOST`, `NUROPB_RMQ_PORT`, `NUROPB_RMQ_USER`, `NUROPB_RMQ_PASSWORD`.

## Run

**Terminal 1 — subscriber first** (exclusive queue; must be bound before publish):

```bash
python examples/vanilla_topic/subscriber.py
# only errors:
python examples/vanilla_topic/subscriber.py 'logs.error'
# everything on the exchange:
NUROPB_RMQ_BINDING_KEY='#' python examples/vanilla_topic/subscriber.py
```

**Terminal 2 — publisher:**

```bash
python examples/vanilla_topic/publisher.py
```

With the default binding `logs.*`, all three sample keys match (`logs.info`,
`logs.error`, `logs.debug`):

```text
[publisher] logs.info -> b'info: started'
…
[subscriber] logs.info -> 'info: started'
[subscriber] logs.error -> 'error: boom'
[subscriber] logs.debug -> 'debug: detail'
```
