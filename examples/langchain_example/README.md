# Example: LangChain agent calling a mesh service tool

Self-standing mini project: a LangChain tool-calling agent looks up **order
status** via a remote mesh service (`orders.get_status`) using a thin
`mesh_service_tool` adapter over nuropb-rmq.

The LLM supplies tool arguments; the adapter validates them (reject, never
coerce), issues one JSON-RPC request on the mesh, and returns the result or a
structured error as a tool observation.

```text
agent.py  --tool-->  mesh_service_tool  --RPC orders.get_status-->  nr.mesh  -->  worker.py
agent.py  <--observation----------------  <--JSON-RPC result/error----------------  worker.py
```

## Prerequisites

- RabbitMQ listening (default `127.0.0.1:5672`, user `guest` / `guest`)
- Sync deps **in this directory** (keeps LangChain out of the root package):

```bash
cd examples/langchain_example
uv sync
```

From the repo root you can also run with:

```bash
uv run --project examples/langchain_example python examples/langchain_example/…
```

Optional broker overrides: `NUROPB_RMQ_HOST`, `NUROPB_RMQ_PORT`, `NUROPB_RMQ_USER`,
`NUROPB_RMQ_PASSWORD` (also loadable from `.env`).

## Secrets (`.env`)

```bash
cp examples/langchain_example/.env.example examples/langchain_example/.env
# edit .env — seed at least one provider key
```

| Variable | Used by |
|----------|---------|
| `NUROPB_LLM_PROVIDER` | `openai` / `claude` / `grok` (default in example: `claude`) |
| `NUROPB_LLM_MODEL` | Optional model override |
| `ANTHROPIC_API_KEY` | Claude |
| `OPENAI_API_KEY` | OpenAI |
| `XAI_API_KEY` | Grok (xAI OpenAI-compatible API) |

`.env` is gitignored. Do not commit real keys. Shell env wins over `.env`.

## Run (two terminals)

**Terminal 1 — worker first:**

```bash
uv run --project examples/langchain_example python examples/langchain_example/worker.py
```

Expected:

```text
[worker] listening identity='orders' methods=['get_status'] mesh='nr.mesh' (Ctrl-C to stop)
```

**Terminal 2 — smoke (no LLM key):**

```bash
uv run --project examples/langchain_example python examples/langchain_example/agent.py --smoke
```

Exercises: good lookup (`ORD-1001`), validation reject (extra field), unknown
order error observation.

**Terminal 2 — live agent** (reads provider/key from `.env`; default `claude`):

```bash
uv run --project examples/langchain_example python examples/langchain_example/agent.py
```

Override provider without editing `.env`:

```bash
uv run --project examples/langchain_example \
  python examples/langchain_example/agent.py --provider openai

uv run --project examples/langchain_example \
  python examples/langchain_example/agent.py --provider grok
```

Error-as-observation demo (unknown order):

```bash
uv run --project examples/langchain_example \
  python examples/langchain_example/agent.py --error-demo
```

Known fixture ids: `ORD-1001` (shipped), `ORD-1002` (processing),
`ORD-1003` (cancelled). Optional: `--order-id ORD-1002`.

## Contracts

- **One tool ↔ one `service.method`** — `orders_get_status` → `orders.get_status`.
- **Single schema source** — `schema.GetStatusParams` shared by adapter and worker.
- **Reject, never coerce** — invalid LLM args become an `INVALID_PARAMS`
  observation; nothing is sent on the wire.
- **One outcome per invocation** — adapter does not auto-retry across
  correlation ids; mesh redelivery may resolve the same id; an agent re-call
  is a new id.
- **Errors are observations** — JSON-RPC / connection errors map to a single
  structured tool observation (`error`, `code`, `code_name`, `message`,
  `retryable`), not an exception out of the agent loop.
- **Idempotent handler** — worker caches by `order_id` (read-only lookup).

## Layout

| File | Role |
|------|------|
| `adapter.py` | `mesh_service_tool` → async `StructuredTool` |
| `llm.py` | openai / claude / grok factory |
| `worker.py` | mesh service `orders.get_status` |
| `agent.py` | smoke + live tool-calling agent |
| `schema.py` | shared params / result models |
| `sample_orders.py` | fixture catalog |
| `_common.py` | broker config, names, stdlib `.env` loader |
| `.env.example` | placeholder keys (copy to `.env`) |

## Out of scope here

Mesh discovery → auto toolbelt, MCP-over-AMQP, JWT claims headers, streaming
tool results, SpeC++/Lean lifts, multi-service toolbelts.
