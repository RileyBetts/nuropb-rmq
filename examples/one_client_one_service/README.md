# Example: one client + one service

Demonstrates three patterns against a local RabbitMQ broker:

1. **Discovery** — service announces methods on `nr.mesh.registry`; client lists them
2. **RPC** — client request/response over mesh exchange `nr.mesh`
3. **Events** — service publishes JSON-RPC notifications on fanout `nr.demo.events`;
   client receives them on a separate subscription

```text
client.py  --RPC-->  nr.mesh  -->  service.py
client.py  <--reply--             service.py
client.py  <--events-- nr.demo.events <--  service.py
client.py  <--advertise-- nr.mesh.registry <--  service.py
```

## Prerequisites

- RabbitMQ listening (default `127.0.0.1:5672`, user `guest` / `guest`)
- Editable install from the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Optional env overrides: `NUROPB_RMQ_HOST`, `NUROPB_RMQ_PORT`, `NUROPB_RMQ_USER`,
`NUROPB_RMQ_PASSWORD`.

## Run (two terminals)

**Terminal 1 — service first:**

```bash
python examples/one_client_one_service/service.py
```

Expected:

```text
[service] listening identity='demo' methods=['ping', 'echo'] mesh='nr.mesh' events='nr.demo.events' (Ctrl-C to stop)
```

**Terminal 2 — client:**

```bash
python examples/one_client_one_service/client.py
```

Expected (abridged):

```text
[client] waiting for registry advertisement…
[client] discovered service='demo' methods=['ping', 'echo'] queue='nr.svc.demo'
[client] RPC demo.ping -> {'pong': True}
[client] RPC demo.echo -> {'echo': {'hello': 'world'}}
[client] event demo.request_handled {...}
[client] event demo.request_handled {...}
[client] done
```

Stop the service with Ctrl-C when finished.

## Notes

- Registry discovery is a **convenience**, not authorization. Broker ACLs and the
  library namespace bind guard remain the security gates.
- The service re-announces on the registry fanout every few seconds so a client
  that starts later still sees advertised methods (fanout is not retained).
- No JWT claims or TLS in this example — see the README AMQPS / claims sections
  for those.
