# nuropb-rmq vs. Celery — competitor assessment

Detailed comparison of nuropb-rmq (v0.2.0) against
[celery/celery](https://github.com/celery/celery), plus an assessment of the
commercial/enterprise support ecosystem around Celery. All figures and claims
below are from primary sources checked directly (GitHub API, README, repo
contents) — not recalled from training data.

## Snapshot

| | Celery | nuropb-rmq |
|---|---|---|
| Category | Distributed task queue / background job framework | AMQP 0-9-1 transport + JSON-RPC 2.0 mesh library |
| First released | 2009 | 2026 (alpha, v0.2.0) |
| Stars / forks | 28,786 / 5,131 | — (new, unlisted) |
| Contributors (top page) | 30+ (paginated — not a total) | small/single maintainer |
| Open issues | 800 | — |
| License | BSD-style (repo reports `NOASSERTION` via API; see `LICENSE` file) | Apache-2.0 |
| Broker/transport | Pluggable via `kombu`: RabbitMQ, Redis, Amazon SQS, GCP Pub/Sub, Azure Service Bus/Storage Queues, Kafka (Confluent), MongoDB, SQLAlchemy, Zookeeper, Consul, etcd, filesystem, memory | RabbitMQ / AMQP 0-9-1 only, hand-rolled wire codec, no transport abstraction |
| Concurrency model | Prefork (multiprocessing), Eventlet, gevent, threads, solo — **no native asyncio pool** (`celery/concurrency/` has no `asyncio.py`) | asyncio-native throughout, single-process, no multiprocessing |
| Correctness approach | 15+ years of production battle-testing, large test suite | SpeC++ SMT CheckSat + Lean proofs of the connection/channel/session state machines specifically (not task semantics or end-to-end delivery) |

## Architecture / mental model

Celery is a **generic background-job system**: a client enqueues a task
message, a broker (RabbitMQ/Redis/SQS/etc.) holds it, and a pool of worker
processes pulls and executes it — fire-and-forget by default, with an
optional, separately-configured **result backend** if the caller wants the
return value back. Built-in orchestration primitives (`docs/userguide/canvas.rst`):
chains, groups, chords, chunks, map/starmap. Built-in scheduling
(`docs/userguide/periodic-tasks.rst`, the `beat` process) for cron-like
recurring tasks.

nuropb-rmq is not a task queue in this sense. It's a thin AMQP client plus a
**request/response RPC and event-notification pattern layer**
(`MeshService`/`RpcClient`/`RpcServer`, JSON-RPC 2.0 shape, correlation IDs,
exclusive reply queues). There is no task orchestration DAG, no periodic
scheduler, and no generic "enqueue arbitrary work, check back later" model —
the RPC call *is* the primary interface, not a bolt-on result backend.

**Point of genuine overlap:** Celery does ship an `rpc://` result backend
(`celery/backends/rpc.py`) that, like nuropb, uses a reply-to header and one
reply queue per client — structurally similar to nuropb's RPC pattern. The
real differences are (a) Celery's own docs flag `rpc://` as not durable across
client restarts and incompatible with chords, since it's a secondary feature
bolted onto the generic task-result abstraction, not the primary calling
convention; and (b) nuropb's publish leg is now backed by publisher confirms
and nack→DLX (v0.2.0), giving the request side an explicit at-least-once
story that Celery's task model leaves to the broker's ack semantics and the
task author's own idempotency/retry logic.

## Concurrency: the concrete "why not just use Celery" for async-native code

Verified directly: `celery/concurrency/` contains `prefork.py`, `eventlet.py`,
`gevent.py`, `solo.py`, `thread.py`, `asynpool.py` — no asyncio pool. Running
Celery from an asyncio application means either a separate sync worker pool
process model, or greenlet monkey-patching via eventlet/gevent. nuropb-rmq is
asyncio end-to-end — connect, publish, consume, RPC all `await`, in the same
event loop as the calling application, no process pool, no monkey-patching.
For a team already standardized on asyncio (FastAPI, aiohttp, etc.) wanting
low-latency service-to-service RPC without spinning up a separate worker-pool
deployment, this is the sharpest architectural distinction.

## Feature areas where Celery is categorically ahead (and nuropb doesn't compete)

- **Broker portability.** `kombu` abstracts ~15 transports; nuropb is
  deliberately RabbitMQ-only with no abstraction layer — a design choice, not
  an oversight, but it rules out ever being a drop-in Celery replacement for
  teams on Redis/SQS/Kafka.
- **Workflow orchestration** (chain/group/chord/chunks/map) — nuropb has none.
- **Scheduling** (`beat`) — nuropb has none.
- **Result backends** — Celery has ~15 pluggable stores (Redis, DB,
  memcached, Cassandra, Elasticsearch, S3, GCS, DynamoDB, etc.); nuropb only
  returns results via a live RPC call, no persisted result store.
- **Monitoring/ops tooling** — Flower (7,226 stars, actively maintained,
  pushed within the last few days as of this check) gives Celery a real-time
  web admin/monitor; nuropb has no equivalent, and is alpha-stage generally.
- **Framework integration packages** — Django, Flask, FastAPI, Pyramid,
  Tornado all have first-class or "not needed" (built-in) integration paths.
  nuropb has none of this ecosystem yet.
- **Cross-language protocol** — Celery's wire protocol has independent
  client implementations in Node.js, PHP, Go, and Rust. nuropb is Python-only
  with no published protocol spec beyond "JSON-RPC 2.0 over AMQP" as an
  internal convention.
- **Track record.** 800 open issues and a top page of 30+ contributors (that
  endpoint is paginated, so this is "most active by commits," not a total)
  reflect enormous real-world adoption and a correspondingly large surface of
  edge cases already found and fixed. nuropb has none of that mileage yet —
  which cuts both ways: less battle-tested, but also a much smaller,
  more auditable surface (the whole protocol layer is ~1,500 lines).

## Where nuropb-rmq has a real, defensible edge

- **Delivery guarantees at the transport layer, not bolted on.** Publisher
  confirms, `connection.blocked` handling with fail-fast publish refusal, and
  `basic.nack`/DLX for poison messages are wired into the client itself
  (v0.2.0). Celery's equivalent guarantees are split across broker
  configuration (`acks_late`, prefetch), task-level retry decorators, and
  whatever the chosen result backend supports — correct, but assembled by the
  application author rather than provided as a cohesive default.
- **No multiprocessing/worker-pool operational overhead.** One asyncio
  process, no prefork/billiard, no separate result-backend service to run and
  monitor.
- **Formal verification — narrow but real.** SpeC++ SMT CheckSat and Lean
  proofs cover the connection/channel/session state machines (illegal AMQP
  transitions, reconnect invariants, heartbeat bounds) — a genuinely
  different correctness methodology from Celery's test-suite-driven approach.
  Scope this claim precisely: it does **not** cover task semantics, canvas
  orchestration equivalents, or end-to-end delivery — nuropb has none of
  those features to verify. It's a differentiator for the protocol layer
  specifically, not a blanket "more correct than Celery" claim.
- **Security posture out of the box.** Named TLS profiles
  (`tls-verify-full`, `tls-verify-custom-san`, dev-only insecure), mTLS via
  SASL `EXTERNAL`, PEM/PKCS#12/secrets-hook material, and JWT claims on RPC
  calls are first-class, documented concepts. Celery's security model is
  largely broker-delegated and configured per-transport.

## Commercial / enterprise support around Celery

There is **no dedicated commercial-support company for Celery**. The
project's own README states plainly: *"Celery is a project with minimal
funding."* The funding/support picture, verified directly:

- **Open Collective** — community donations fund ongoing maintenance; this is
  funding, not a support contract.
- **Tidelift** — the README still carries a "For enterprise / Available as
  part of the Tidelift Subscription" banner linking to
  `tidelift.com/subscription/pkg/pypi-celery`. Checked directly: that URL
  **redirects (301) to a generic SonarSource security-solutions page**, not a
  live Celery-specific subscription page. Tidelift's original per-package
  subscription product appears to have been folded into SonarSource's
  broader offering; the README banner is stale boilerplate rather than a
  live, celery-specific commercial-support channel today.
- **Infrastructure sponsors, not support vendors:** Blacksmith (CI
  infrastructure), CloudAMQP ("industry leading RabbitMQ as a service...
  24,000+ running instances," explicitly positioned in the README as the
  recommended way to get started with a hosted broker), Upstash (serverless
  Redis), Dragonfly (Redis-compatible in-memory store). These companies
  sponsor the project and are the de facto commercial ecosystem people pair
  with self-hosted Celery — hosted broker/store, not Celery itself.
- No official enterprise SLA, paid support tier, or Celery-branded consulting
  arm exists from the maintaining team. Third-party consulting exists (as it
  does for any popular OSS project) but isn't an official channel.

**Net picture:** Celery is a case of enormous adoption (28.8k stars, used
across the Python ecosystem for over a decade) riding on thin, volunteer-
funded maintainership, with the commercial layer entirely outsourced to
adjacent infrastructure vendors (CloudAMQP et al.) rather than the project
itself. That gap — high dependency-criticality, no dedicated support vendor —
is a known pattern in mature OSS infra, and it's the most concrete opening
for anything positioning against Celery commercially, not a feature gap.

## Positioning takeaway

nuropb-rmq should not try to compete with Celery on Celery's own terms — task
orchestration, scheduling, broker portability, and ecosystem breadth are a
15-year head start that isn't closeable via feature parity. The defensible
position is narrower and different in kind:

- **Not a Celery replacement.** For background/scheduled job processing with
  DAG orchestration, Celery is the right tool and nuropb doesn't compete.
- **A purpose-built alternative for one specific pattern Celery does
  awkwardly:** low-latency, asyncio-native, synchronous-style RPC and
  event pub/sub between services that are already committed to RabbitMQ,
  without needing a separate result backend, a worker-pool process model, or
  `kombu`'s generic transport abstraction.
- **Realistic deployment story:** nuropb living *alongside* Celery in the
  same stack — Celery for background/periodic work, nuropb for the
  service-to-service RPC/event fabric — is more credible than positioning it
  as a wholesale replacement.
- **Commercial angle, if pursued:** Celery's own commercial ecosystem is
  entirely infra-sponsor-driven (CloudAMQP hosting RabbitMQ, paired with the
  client library). The same playbook — a managed-RabbitMQ vendor sponsoring
  or endorsing a formally-verified client purpose-built for their broker —
  is a more plausible enterprise motion for nuropb than trying to replicate
  Celery's own (currently defunct) Tidelift-style subscription.
