# Using nuropb-rmq under LangGraph

OSS LangGraph stays an in-process graph engine. nuropb-rmq is the
**cross-process call fabric** (JSON-RPC over RabbitMQ), not a LangSmith /
Agent Server replacement and not a checkpoint store — Postgres (or whatever
you already use) stays the checkpointer.

Runnable demo: [`examples/langgraph_example/`](../../examples/langgraph_example/).
The adapter (`remote_node`) is **example-local** on purpose: LangGraph is not
a core extra.

## Retry-authority split

```text
mesh redelivery     — while the client reply queue exists
Session (default)   — park-and-retry of the same Future (at-least-once republish)
adapter             — CONNECTION_LOST only under fail_outstanding=True → rebind
LangGraph           — checkpoint replay when the adapter raises RetriableRemoteError
remote handler      — must be idempotent (keyed by business id, not AMQP tag)
```

Default reconnect parks in-flight RPCs. Fail-fast (`fail_outstanding=True`)
keeps a single application-owned retry path. See [Reconnect](../concepts/reconnect.md).

## What the adapter must do

1. Map `RpcError` with `CONNECTION_LOST` to a **retriable** graph error.
2. Rebind (new `Session` / `mesh.rebind()`) before LangGraph replays the node.
3. Slice graph state with declared `reads=` / `writes=`; reject undeclared or
   non-JSON values (no coerce).
4. Treat `PUBLISH_RETURNED` as a routing miss (service not bound), not as
   connection loss — do not replay blindly; bind/start the worker.

LangChain follows the same split (`examples/langchain_example/`): one tool →
one `service.method`; the adapter never auto-retries across correlation ids.

## Honest limits

- RabbitMQ is not a `BaseCheckpointSaver`.
- HITL interrupt/resume, streaming progress, and sub-agent queues can be
  built from the same RPC/event primitives — they stay examples, not new
  library layers, until a second real consumer needs them.
- A2A/MCP-over-AMQP is an ecosystem bet, not this package.
