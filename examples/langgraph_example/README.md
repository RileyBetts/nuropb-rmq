# Example: LangGraph remote invoice extraction

Self-standing mini project: a LangGraph pipeline offloads **invoice field
extraction** to a remote worker over nuropb-rmq mesh RPC (`invoices.extract`).

Local nodes ingest / classify / validate. The extract step runs in another
process via a thin `remote_node` adapter — the OSS LangGraph engine stays
single-process; the mesh supplies the cross-process call.

```text
graph.py  --RPC invoices.extract-->  nr.mesh  -->  worker.py
graph.py  <--JSON-RPC result-------             worker.py
```

## Prerequisites

- RabbitMQ listening (default `127.0.0.1:5672`, user `guest` / `guest`)
- Sync deps **in this directory** (keeps LangGraph out of the root package):

```bash
cd examples/langgraph_example
uv sync
```

From the repo root you can also run with:

```bash
uv run --project examples/langgraph_example python examples/langgraph_example/…
```

Optional env overrides: `NUROPB_RMQ_HOST`, `NUROPB_RMQ_PORT`, `NUROPB_RMQ_USER`,
`NUROPB_RMQ_PASSWORD`.

## Run (two terminals)

**Terminal 1 — worker first:**

```bash
uv run --project examples/langgraph_example python examples/langgraph_example/worker.py
```

Expected:

```text
[worker] listening identity='invoices' methods=['extract'] mesh='nr.mesh' (Ctrl-C to stop)
```

**Terminal 2 — happy-path graph:**

```bash
uv run --project examples/langgraph_example python examples/langgraph_example/graph.py
```

Expected (abridged):

```text
[graph] ingest document_id='inv-1001'
[graph] classify doc_type='invoice'
[graph] extract (remote) document_id='inv-1001'
[worker] extract document_id='inv-1001' vendor='Acme Supplies Ltd' total=32.5
[graph] validate valid=True vendor='Acme Supplies Ltd' total=32.5 errors=[]
[graph] done valid=True vendor='Acme Supplies Ltd' total=32.5 currency='GBP'
```

Optional document id: `graph.py inv-1002`.

## Reconnect demo (optional)

Shows the retry-authority split: when the **client** connection drops mid-call,
the adapter surfaces a retriable error, rebinds the session, and LangGraph
replays the extract node from checkpoint (fresh correlation id). The worker
stays up.

```bash
uv run --project examples/langgraph_example python examples/langgraph_example/reconnect_demo.py
```

Expected markers: `forcing client disconnect`, `CONNECTION_LOST`, `rebound`,
`replay extract`, then `done valid=True`.

## Contracts

- **Idempotent remote handlers** — keyed by `document_id`. Mesh at-least-once
  redelivery and LangGraph replay can run extract more than once.
- **Retry authority** — mesh redelivery while the client reply queue exists;
  LangGraph checkpoint replay only after `CONNECTION_LOST`. The adapter does
  not local-retry.
- **State boundary** — `reads=` / `writes=` on `remote_node`; reject undeclared
  or non-JSON values (no coerce).

## Layout

| File | Role |
|------|------|
| `adapter.py` | `remote_node` wrapper |
| `worker.py` | mesh service `invoices.extract` |
| `graph.py` | happy-path LangGraph |
| `reconnect_demo.py` | connection-loss → rebind → replay |
| `sample_invoices.py` | fake invoices (no OCR/LLM) |
| `_common.py` | broker config + method names |

## Out of scope here

Streaming partial progress, JWT claims headers, checkpoint storage on RabbitMQ,
`remote_tool`, SpeC++/Lean lifts, real OCR/LLM.
