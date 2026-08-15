# Opportunities & marketing positioning

Internal strategy notes for how to talk about nuropb-rmq without looking like a
direct competitor to Celery, LangGraph/LangSmith, or general-purpose AMQP
clients (pika / aio-pika). Companion technical story:
[`adaptability-scalability.md`](adaptability-scalability.md). Product intent and
trust boundaries: [`project-intent.md`](project-intent.md).

Grounded in the three overlap assessments at repo root plus short external
checks (RabbitMQ scale docs, MCP/A2A transport specs, adjacent Python
categories). Claims that are alpha-stage or scoped are marked as such.

---

## Category statement

**nuropb-rmq is distributed service routing and event fabric infrastructure
over RabbitMQ.**

It is an asyncio-native Python AMQP 0-9-1 client (no pika at runtime) with
JSON-RPC 2.0 mesh patterns on top: request/reply RPC, topic/fanout event
pub-sub, `service.method` bind, and optional JWT claims on RPC. Horizontal
scale comes from RabbitMQ (more service instances and consumers on a shared
broker), not from prefork worker pools. Other languages and frameworks already
speaking AMQP (or JSON-RPC-shaped payloads) can participate on the same fabric
without adopting this library.

“Mesh” here means application-level JSON-RPC over a shared broker — not Istio /
Linkerd. See [`docs/concepts/service-mesh.md`](../docs/concepts/service-mesh.md).

“Event fabric” means durable event routing / pub-sub (JSON-RPC notifications
over topic/fanout) — not classic CQRS event sourcing (append-only log + replay
store). Do not market EventStore-style claims unless that product story is
built later.

---

## Anti-positioning map

Lead with coexistence. Overlap is real; category is different.

| Adjacent product | What they own | How we sit relative to them |
|---|---|---|
| **Celery** (and Dramatiq / Taskiq / RQ) | Background jobs, canvas/DAG orchestration, beat scheduling, pluggable brokers via kombu-class abstractions | **Beside, not instead.** Celery for deferred/periodic work; nuropb for low-latency service-to-service RPC and events on RabbitMQ, in the same asyncio process as the app. |
| **LangGraph / LangChain OSS** | In-process graph engine, tools, checkpointers | **Under the agents.** Fill the OSS gap for cross-process / cross-service agent calls, durable HITL resume channels, and progress event buses — without replacing LangGraph itself. |
| **LangSmith / LangGraph Platform (Agent Server)** | Commercial deploy, Redis+Postgres task queue, hosted tracing | **Not a competitor pitch.** Self-host shops already on RabbitMQ may use nuropb as an alternative *transport* path; never claim “gap in OSS LangGraph” for paid-product internals. |
| **pika / aio-pika** | General-purpose AMQP clients (full method surface, admin/management) | **Purpose-built subset + patterns.** Continuous consume + declare-your-own topology + mesh RPC/events; intentional non-goals for `basic.get`, Tx, purge/delete admin APIs. Not “pika but better at everything.” |
| **Nameko** | Opinionated Python microservices framework (RPC/events over AMQP, eventlet) | **Different concurrency and trust story.** Nameko is a service framework; nuropb is a library (asyncio + optional mesh patterns + proof fabric). Same broker neighborhood, different product shape. |
| **Temporal / Prefect / workflow engines** | Durable workflow orchestration, timers, activity retries | **Out of category.** No canvas, no workflow DSL. Agents or services may *call into* a nuropb mesh; orchestration stays elsewhere. |

---

## Opportunity wedges (defensibility order)

### 1. Asyncio service RPC + events on an existing RabbitMQ estate

**Audience:** Teams on FastAPI / aiohttp / asyncio apps that already run
RabbitMQ (often alongside Celery for jobs).

**Pitch:** One process, one event loop — `await` connect, publish, consume, and
RPC without a separate prefork worker fleet or greenlet monkey-patching.
Publisher confirms, `connection.blocked` fail-fast, and nack→DLX are wired
into the client (v0.2.0), so delivery posture is a cohesive default rather
than assembled from broker knobs + task decorators + result backends.

**Do not say:** “Celery replacement.”

**Source:** [`celery-competitor-assessment.md`](celery-competitor-assessment.md).

### 2. Cross-process agent / tool mesh with JWT claims

**Audience:** LangGraph / DeepAgents / custom agent runtimes that need backends
as separate services.

**Pitch:** OSS LangGraph is single-process networking-wise (no broker in core
deps). `MeshService` / `RpcClient` / `service.method` routing is a ready durable
RPC mesh. Optional JWT claims (`nr.claims` headers; `exp` / `jti`↔correlation /
`method` binding) give claim-based security for agent → backend calls without
polluting the JSON-RPC body.

**Needs (honest):** Thin adapter + ownership of reconnect (`CONNECTION_LOST` →
`mesh.rebind()`). That state machine is the integrator’s, by design.

**Do not say:** “LangSmith alternative” or “replaces Agent Server.”

**Source:** [`langchain-langgraph-opportunity-assessment.md`](langchain-langgraph-opportunity-assessment.md),
[`docs/concepts/jwt-claims.md`](../docs/concepts/jwt-claims.md).

### 3. Durable HITL bridge, progress events, queued sub-agents

Natural extensions of the same mesh primitives:

- **HITL:** exclusive reply queues + correlation + at-least-once publish as a
  durable “notify human, wait, resume” channel stronger than a bare webhook.
- **Progress bus:** topic/fanout events for node-transition / progress signals
  decoupled from proprietary tracing.
- **Sub-agent-as-job:** long-running or sandboxed work benefits from confirms +
  poison-message → DLX rather than in-process async that dies with the parent.

Still complementary to LangGraph checkpoints (Postgres stays; RabbitMQ is not a
checkpoint store).

### 4. A2A / MCP over AMQP (secondary ecosystem bet)

Both specs sanction custom transports while keeping JSON-RPC (or A2A’s abstract
operations) intact:

- MCP: transport-agnostic; custom transports MUST preserve JSON-RPC message
  format and lifecycle ([MCP transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)).
- A2A: custom protocol bindings are an explicit extension point (URI-identified
  in Agent Card `supportedInterfaces`; see A2A custom bindings docs).

**Pitch:** durable, ordered, VPC/air-gapped agent messaging where inbound HTTP
is undesirable. Secondary to wedges 1–3 — ecosystem bet, not a documented hole
in LangChain’s own OSS frameworks. Note: CloudAMQP’s `a2a-amqp` already explores
AMQP for A2A task/event scaling; position as aligned neighborhood, not as
owning that category yet.

### 5. Broker-vendor adjacency (commercial motion)

Celery’s commercial layer is infra-sponsor-driven (hosted RabbitMQ / Redis),
not a Celery Inc. support company. Same playbook is plausible for nuropb: a
managed-RabbitMQ vendor endorsing a formally-verified, asyncio, mesh-oriented
client purpose-built for their broker — sponsorship/endorsement, not “we beat
Celery on Flower.”

---

## Proof fabric as trust marketing

This is the differentiator peers in the assessments do not offer.

**What to say**

- Protocol, session, and pattern behaviour is backed by **SpeC++ SMT CheckSat**
  and **Lean proofs**, gated in CI — not only unit tests.
- Scope: connection/channel/session state machines, correlation invariants,
  reconnect fail-fast clearing, mesh namespace bind guards, config durable↔
  `delivery_mode` pairing, publisher confirms / delivery settle models as
  covered in [`specs/lean/`](../specs/lean/) and [`specs/specpp/`](../specs/specpp/).
- Trust story pairs with explicit TLS profiles, mTLS / SASL `EXTERNAL`, and
  broker ACL as the hard authorization gate.

**What never to say**

- “Formally verified end-to-end delivery” or “more correct than Celery at
  tasks” — proofs do not cover task DAGs, canvas, or broker partition
  tolerance.
- “Proofs authorize who can bind” — broker ACLs are external; Lean covers
  client-side guards given correct deployment permissions
  ([`project-intent.md`](project-intent.md) trust boundary).
- “JWT crypto is proved” — crypto is axiomatized; verification of claims
  structure/binding is in scope, issuance/revocation is IdP’s job.
- Uniqueness absolutism (“the only verified messaging stack”) — research
  libraries verify other protocols in Coq; among **production AMQP / RabbitMQ
  Python clients**, SpeC++ + Lean as a marketed CI gate is effectively absent.
  Prefer: “unusual for this category” over “unique in all of computing.”

---

## Message house (copy seeds)

Short phrases for posts, README hero, or docs homepage. Tone: precise, not
triumphal.

**Category line**

> Asyncio service routing and event fabric on RabbitMQ — JSON-RPC mesh patterns,
> AMQP-interop, formally checked protocol/session behaviour.

**Single-threaded / scale**

> Proudly single-threaded asyncio. Concurrency complexity stays low in-process;
> horizontal scale comes from RabbitMQ.

**Coexistence**

> Not a Celery replacement. Use Celery for background and scheduled jobs; use
> nuropb-rmq for service-to-service RPC and events on the broker you already run.

**Agents**

> A natural backend for agent task execution against a service mesh — with
> optional JWT claim-based security on every RPC.

**Proof**

> SpeC++ CheckSat and Lean proofs of the connection, channel, and session state
> machines — CI-gated, scoped, and honest about what the broker still owns.

**Interop**

> AMQP 0-9-1 on the wire and JSON-RPC 2.0 envelopes — so other frameworks and
> languages can join the same fabric without speaking Python.

**Mesh clarification**

> “Mesh” means JSON-RPC over a shared RabbitMQ broker. Discovery never
> authorizes binds; broker ACLs do.

---

## Honest limits (say these early)

- **Alpha** (v0.2.0): public API may still change; not battle-tested at Celery
  scale or age.
- **Python-only client today:** interop is via AMQP + envelope conventions, not
  multi-language SDKs yet.
- **RabbitMQ / AMQP 0-9-1 only:** deliberate; no kombu-style transport zoo.
- **Intentional AMQP subset:** no admin/management methods; documented
  non-goals in queue profiles. v0.5.0 closed `basic.return`, the remaining
  content properties, and `update-secret` — see
  [`amqp-completeness-v0.2.0-vs-pika.md`](amqp-completeness-v0.2.0-vs-pika.md).
- **No job orchestration / beat / result-store zoo** — by design.
- **Coexist, don’t replace** is the credible deployment story.

---

## Adjacent landscape (one-liners for category clarity)

| Category | Examples | Boundary line |
|---|---|---|
| General AMQP clients | pika, aio-pika, amqplib, rabbitmq clients in other langs | Wire access; we add asyncio-native subset + mesh patterns + proofs |
| Task / job queues | Celery, Dramatiq, Taskiq, RQ | Enqueue work, workers pull; we do live RPC/events as primary API |
| Microservice frameworks | Nameko | Full framework + eventlet; we are a library in your asyncio app |
| Workflow engines | Temporal, Prefect | Durable workflows; we are the mesh/routing layer under services or agents |
| Agent frameworks | LangGraph, DeepAgents | Graphs/tools in-process; we carry calls and events across processes |

---

## Sources

**Internal assessments**

- [`celery-competitor-assessment.md`](celery-competitor-assessment.md)
- [`langchain-langgraph-opportunity-assessment.md`](langchain-langgraph-opportunity-assessment.md)
- [`amqp-completeness-v0.2.0-vs-pika.md`](amqp-completeness-v0.2.0-vs-pika.md)

**Product / trust**

- [`project-intent.md`](project-intent.md)
- [`adaptability-scalability.md`](adaptability-scalability.md)
- [`docs/concepts/service-mesh.md`](../docs/concepts/service-mesh.md)
- [`docs/concepts/jwt-claims.md`](../docs/concepts/jwt-claims.md)
- [`specs/lean/CORRESPONDENCE.md`](../specs/lean/CORRESPONDENCE.md)
- [`README.md`](../README.md) (formal verification section)

**External (spot-checked for this note)**

- RabbitMQ production / clustering guidance:
  https://www.rabbitmq.com/docs/production-checklist
- MCP transports (custom / transport-agnostic):
  https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- A2A custom protocol bindings:
  https://a2a-protocol.org/dev/topics/custom-protocol-bindings/
- Nameko “what is Nameko”:
  https://nameko.readthedocs.io/en/stable/what_is_nameko.html
