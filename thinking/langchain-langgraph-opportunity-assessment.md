# nuropb-rmq × LangChain / LangGraph / LangSmith — opportunity assessment

Evaluation of what gaps nuropb-rmq (async AMQP 0-9-1 client + JSON-RPC mesh
patterns for RabbitMQ) could fill in LangChain's open source frameworks
(LangChain, LangGraph, DeepAgents), and adjacent opportunities in the
LangSmith / LangGraph Platform and agent-protocol (A2A, MCP) ecosystem.

Claims below are grounded in primary sources actually checked (repo contents,
`pyproject.toml` dependency lists, current docs, protocol specs) — not
recalled from training data.

## Grounding

- `langgraph` core's own `pyproject.toml` deps: `langchain-core`,
  `langgraph-checkpoint`, `langgraph-sdk`, `langgraph-prebuilt`, `xxhash`,
  `pydantic` — zero networking/messaging libraries. Confirmed: the OSS graph
  engine is single-process; multi-agent supervisor/swarm/network patterns are
  Python function calls and shared state, not network calls.
- The Redis+Postgres task queue described for scaling agent runs is real, but
  it lives under `docs.langchain.com/langsmith/agent-server` — that's
  LangSmith Deployment (commercial), not the OSS `langgraph` package.
  `langgraph-cli` (MIT) gives you `langgraph dev`/`up` for local/dev;
  production-grade distributed queueing isn't shipped as OSS source.
- `langgraph-messaging-integrations` in the `langchain-ai` org is Slack/chat-
  platform bridging, not a message-broker integration — confirms there's no
  RabbitMQ/Kafka/AMQP integration anywhere in the org.
- A2A spec (§5.8): custom transport bindings are an explicit, sanctioned
  extension point (URI-identified, must follow error-mapping/data-type
  conventions).
- MCP spec (transports section): the protocol is explicitly "transport-
  agnostic... can be implemented over any communication channel that supports
  bidirectional message exchange," with stdio and Streamable HTTP as the only
  two *standard* transports today; custom transports are sanctioned as long as
  JSON-RPC message format and lifecycle are preserved.

## Real gaps in the OSS frameworks

**1. Cross-process / cross-service agent mesh.**
OSS LangGraph has no answer for "agent A and agent B run as separate
processes/services." nuropb's `MeshService` / `ServiceIdentity` /
`RpcClient`-`RpcServer` (`service.method` routing over a shared exchange) is a
ready-made durable RPC mesh for exactly this.
Needs building: a thin LangGraph adapter — a node/tool wrapper that calls out
via `RpcClient` instead of an in-process function, plus ownership of
reconnect (`CONNECTION_LOST` → `mesh.rebind()`). That reconnect handoff is not
cosmetic: nuropb's reconnect is fail-fast, caller-rebinds by design, and
agents that sit idle for hours between steps are exactly the workload that
hits a broker restart mid-idle. Whoever writes the adapter owns that state
machine, not nuropb.

**2. Durable human-in-the-loop bridge.**
`interrupt()`/resume needs *something* external to eventually deliver the
resume value, and OSS ships no reference transport for that "something" beyond
checkpointer state. nuropb's RPC pattern (exclusive reply queues, correlation
tracking, at-least-once via v0.2.0 publisher confirms) is a plausible durable
channel for "notify a human, wait indefinitely, resume on reply" that survives
process/broker restarts — stronger than a bare webhook.

**3. External event bus for agent progress.**
`stream()` is in-process/in-call. Propagating node-transition or progress
events to other services/dashboards decoupled from LangSmith's proprietary
tracing has no OSS story. nuropb's topic/fanout event pub/sub (JSON-RPC
notification shape) fits directly.

**4. Sub-agent-as-queued-job for DeepAgents.**
"Highly autonomous, long-running agents" delegating to slow/sandboxed
sub-agents benefits from a durable, at-least-once queue with poison-message
handling rather than naive async calls that die with the process. v0.2.0's
confirms + `basic.nack`/DLX cover exactly this failure mode.

## Adjacent opportunity, not a framework gap

**Task-queue alternative to Agent Server.**
This isn't filling a hole in OSS LangGraph — it's competing with the
*internals of a commercial product* that OSS users who don't buy LangSmith
Deployment don't get. Real opportunity (shops already standardized on
RabbitMQ over Redis+Postgres get a lighter self-host path), but it should be
pitched as "alternative to a paid product," not "gap in the open source
framework."

## Protocol-ecosystem plays

**5. A2A over AMQP.**
**6. MCP over AMQP.**
Both specs explicitly allow custom transport bindings while keeping JSON-RPC
as the message format — nuropb's mesh is already JSON-RPC-shaped, so this is
"implement a sanctioned extension point," not "invent a non-standard
binding." The pitch: durable, ordered, replayable A2A/MCP over a broker for
VPC-internal or air-gapped deployments where exposing inbound HTTP endpoints
is undesirable, vs. HTTP/SSE's point-to-point, no-retry-by-default model.
langchain.com already advertises "native A2A & MCP support" on the commercial
deployment product — so there's a live audience, but it's currently
HTTP-only there.

## Honest limits before pitching any of this

- **RabbitMQ is not a checkpoint store.** nuropb can't supply a
  `BaseCheckpointSaver` — Postgres stays exactly where it is. nuropb is the
  Redis replacement for people who run RabbitMQ, not the Postgres replacement.
- Python-only, asyncio-only, alpha (v0.2.0) — not something to build a
  cross-language agent mesh on today.
- No `basic.return`/mandatory publishing (flagged in the AMQP-vs-pika
  completeness review, still true as of v0.2.0) — for an RPC mesh
  specifically, this means a misrouted agent call currently has no signal
  path; it should surface as an error rather than silently vanish, and that's
  worth closing before pitching #1 seriously.

## Bottom line

The strongest, most defensible pitch is #1 (agent mesh) plus #2/#3/#4 as
natural extensions of the same mesh primitives — all genuine gaps in the OSS
graph engine, all provable from its dependency list. The A2A/MCP transport
plays are real but secondary; they're ecosystem bets on an extension point,
not a documented hole in LangChain's own frameworks.
