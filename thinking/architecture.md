# Architecture Sketch

Architecture for the project described in `project-intent.md`. Decisions
below are tracked in the Decision ledger; items marked **Decided** are
normative for SpeC++/Lean and for implementation.

**Design drivers.** Per the project's stated goals — trust, robustness, and
highest achievable throughput — every layer below should be read with those
three in mind: state machines and invariants provable enough to establish
trust (Lean layer), explicit handling of failure/reconnect for robustness
(Session layer, Phase 2 proofs), and a hot path free of unnecessary
allocation/copying/abstraction for throughput (Transport/Protocol layers
especially, where nuropb's current `pika`-based overhead lives today). Where
these pull in different directions — e.g. a simpler, more easily provable
design vs. a faster but more complex one — the trade-off should be called out
explicitly in review rather than decided implicitly by whichever gets
written first.

**Governing invariant: no conflation, no multi-path outcomes.** See
`project-intent.md`, "Core architectural invariant," for the full statement.
Every decision below has been checked against it — one authoritative
mechanism per concern, one name/meaning per concept even when a value is
carried in more than one place (correlation id/`id`), and any secondary/
fallback mechanism scoped to be *mutually exclusive* with the primary one
rather than a parallel path that can independently produce a different
outcome (broker TTL vs. client-side timeout). Any new decision made in this
document going forward should be checked the same way before being marked
"decided."

## Decision ledger

Single status view. Detail and rationale live in the sections linked by name.

### Decided

| Decision | One-line |
|---|---|
| Layering | Application → Pattern → Session → Protocol → Transport; Lean parallel |
| Correlation id | One Session value; AMQP `correlation_id` + JSON-RPC `id`; string ≤255 octets; UUID4 hex default; reject invalid |
| Caller-supplied id collision | Reject request if id collides with any outstanding id in the same correlation table (never regenerate) |
| Reply routing | Per-connection exclusive auto-delete reply queue (not direct reply-to) |
| Reply-queue publish auth | Broker-native RabbitMQ permission profile; docs + ops checklist in `scripts/reply-publish-restricted.md` |
| Claims location | AMQP headers only; JSON-RPC body stays spec-pure |
| Claims trust model | Signed JWT bearer in headers; verify signature; require `exp`; bind to request via `method` + `jti` tied to correlation id; fail-closed |
| Mesh-binding authorization | Broker-native vhost/topic permission profile; optional app-level registry is **discovery only** (never replaces broker ACL) || Timeouts | Broker TTL + DLX + `consumer_timeout` authoritative; client-side timeout mutually exclusive fallback |
| Duplicates | At-least-once; first reply wins; later messages for resolved id discarded |
| Error codes | Nuropb taxonomy in `-33000..-33999`; shared `-32000..-32099` used sparingly |
| `error.data` | Allowlisted structured fields only; no stack traces, hostnames, queue names, or raw `x-death` |
| mTLS / SASL | Negotiate from broker ads; support `EXTERNAL` when offered; never assume mTLS ⇒ passwordless |
| Cert sourcing | **Done** — files + in-memory PEM + PKCS#12 (`[pkcs12]` extra) + secrets-manager hook → `TlsMaterial` |
| Cert rotation | Re-invoke secrets hook on **new connection only**; mid-connection cert expiry → orderly reconnect with fresh material |
| Config strategy | **Done** — validated named queue profiles; durable+persistent enforced together |
| Default queue profile | **Done** — `durable-at-least-once`: quorum + persistent + TTL + DLX + `x-delivery-limit` |
| Spec consistency | SpeC++ SMT `CheckSat` before Lean |
| Protocol SM SpeC++ CheckSat | **Passed** — Protocol + Session under `specs/specpp/` (`python specs/specpp/check_sat.py`) |
| Lean Phase 1 Protocol SM | **Done** — `specs/lean/` proves Protocol invariants 1–7 (`lake build`); correspondence in `specs/lean/CORRESPONDENCE.md`; hypothesis PBTs under `tests/protocol/` + `tests/transport/` |
| Session SpeC++ CheckSat | **Passed** — `specs/specpp/Session/correlation.smt2` (sat) + negatives (unsat) |
| Lean Phase 1b Session correlation | **Done** — `NuropbRmq.Session.{Correlation,Invariants}`; id format, dual-accessor, collision reject, first-reply-wins, reply-queue brackets table |
| Lean↔Python (v1) | SpeC++ → Lean model → property-based tests + manual correspondence; no code extraction; **re-audited 2026-08-11** (`specs/lean/CORRESPONDENCE.md` Alignment findings) |
| TTL anti-enumeration | **Goal** (content half covered): allowlisted `error.data` + `tests/patterns/test_anti_enumeration.py`; timing indistinguishability remains ops/deployment |
| Claims compare | Constant-time (`hmac.compare_digest` or equivalent) |
| Sequencing step 1 (Transport+Protocol) | **Done** — native AMQP connect/channel/declare/publish/consume/ack in `src/nuropb_rmq/` (no `pika`) |
| Sequencing step 2 (Lean Phase 1) | **Done** — Protocol SM invariants 1–7 |
| Sequencing step 3 (Session+RPC) | **Done** — exclusive reply queue, correlation table, JSON-RPC client/server, DLQ timeout path |
| Sequencing step 4 (Lean Phase 1b) | **Done** — Session correlation proofs |
| Sequencing step 5 (Events/pub-sub) | **Done** — JSON-RPC notifications over topic/fanout (`patterns/events.py`) |
| Sequencing step 6 (Mesh + claims) | **Done** — namespaced mesh bind + JWT `nr.claims` on RPC; SpeC++ Pattern CheckSat |
| Sequencing step 7 (Reconnect + Lean Phase 2) | **Done** — fail-fast `CONNECTION_LOST`, Session/Mesh rebind, SpeC++ Phase 2, Lean DeadLetterTimeout + Reconnect |
| Throughput benchmark harness | **Done** — `bench/` compares nuropb-rmq vs pika (optional `[bench]` extra); exclusive reply-queue vs `amq.rabbitmq.reply-to` measured, default unchanged |
| Release CI | **Done** — GitHub Actions: SpeC++ CheckSat, unit + claims pytest, RabbitMQ integration, Lean `lake build`; Apache-2.0 |
| Pattern Lean (mesh + claims) | **Done** — `NuropbRmq.Pattern.{Mesh,Claims,Invariants}`; SpeC++ Pattern CheckSat already passed |
| Large-payload RPC 16KB·c1 | **Done** — fair stub-reply bench + coalesced publish/ack drains + fewer receive copies; near parity vs pika (`bench/results/20260811T144045Z.json`) |
| TLS / brew AMQPS verify-full | **Done** — `scripts/gen_amqps_certs.sh`, SSL-context unit tests, opt-in `tests/integration/test_amqps_smoke.py` (PLAIN over TLS, `tls-verify-full`) |
| mTLS / SASL EXTERNAL smoke | **Done** — client cert in cert script; opt-in `test_amqps_mtls_smoke.py`; SASL selection unit tests; never assume mTLS ⇒ passwordless |
| Cert sourcing (PEM + PKCS#12) | **Done** — `tls_material.py`: file / bytes / PKCS#12 / `tls_secrets` hook; re-resolve each `connect()`; EXTERNAL from any cert source; key/password redaction in `repr` |
| Queue profiles | **Done** — `config/queue_profile.py`; RpcServer/Mesh default `durable-at-least-once`; SpeC++ Config CheckSat |
| Config QueueProfile Lean | **Done** — `NuropbRmq.Config.{QueueProfile,Invariants}`; durable↔`delivery_mode` (2026-08-11) |
| Heartbeat watchdog | **Done** — client heartbeat send + missed-peer (2× interval) → `CONNECTION_LOST` |
| Reply-publish docs | **Done** — `scripts/reply-publish-restricted.md` + README |
| Frame fuzz CI | **Done** — `tests/transport/test_frame_fuzz.py` + `pytest -m fuzz` in CI |
| App-level mesh registry (discovery) | **Done** — fanout `nr.mesh.registry`; `MeshService(announce=True)` / `MeshRegistryViewer`; never consulted for bind |

### Deferred (explicit)

| Item | Why deferred |
|---|---|
| In-flight RPC park-and-retry across reconnect | v1 fail-fast only; avoids multi-path outcomes |

## Layering overview

```
┌─────────────────────────────────────────────────────────────┐
│  Application code (services, clients)                       │
├─────────────────────────────────────────────────────────────┤
│  Pattern Layer                                               │
│   - RPC request/reply       (JSON-RPC 2.0 vocabulary)        │
│   - Notifications/pub-sub   (JSON-RPC 2.0 notification shape)│
│   - Mesh registration/binding                                │
│   - Context/claims propagation                               │
├─────────────────────────────────────────────────────────────┤
│  Session Layer                                                │
│   - Correlation tracking (id -> pending future)               │
│   - Timeout / cancellation                                    │
│   - Reconnect & re-binding coordination                       │
├─────────────────────────────────────────────────────────────┤
│  Protocol Layer (AMQP 0-9-1 state machine)                    │
│   - Connection lifecycle (handshake, heartbeat, tune, close)  │
│   - Channel lifecycle (open, flow, close)                     │
│   - Exchange/queue/binding operations                         │
│   - Publish/consume/ack/nack                                  │
├─────────────────────────────────────────────────────────────┤
│  Transport Layer                                               │
│   - TCP socket I/O (asyncio streams)                          │
│   - AMQP frame encode/decode (wire format)                    │
│   - TLS                                                        │
├─────────────────────────────────────────────────────────────┤
│  Lean Spec Layer (parallel, not "below" — see note)           │
│   - Formal models of Protocol Layer state machine              │
│   - Formal models of Session Layer correlation invariants      │
│   - Proofs; not executed at runtime                            │
└─────────────────────────────────────────────────────────────┘
```

The Lean layer isn't literally beneath the others at runtime — it's a
parallel, static artifact: a formal model of the state machines and
invariants that the Transport/Protocol/Session layers implement, proved
correct on paper (well, in Lean), with the Python implementation kept
aligned via property-based tests derived from the model plus manual
correspondence review (v1 coupling — see Decision ledger and "Lean-to-
Python coupling").

## Layer 1: Transport

Responsibility: raw bytes on the wire.

- `asyncio`-based TCP transport (with TLS support, including mutual TLS —
  client certificate presentation and verification, not just server-cert
  verification)
- AMQP 0-9-1 frame codec: encode/decode frame header, method payloads, content
  header/body frames, per the AMQP 0-9-1 spec (this is the part that
  currently comes from `pika`; we own it here)
- No protocol semantics here — just "send frame," "receive frame"

**mTLS specifics:**
- Client certificate + private key loading (**PEM and PKCS#12**), sourced
  from any of: file paths, in-memory bytes/PEM, PKCS#12 (`.p12`/`.pfx`), or a
  pluggable secrets-manager hook (with rotation support) — see "Cert/key
  material sourcing" below for the full decision. Loading is configurable
  independently of the CA bundle
  used to verify the broker's certificate, which can be sourced the same
  flexible way.
- Certificate/key passed through to the connection config alongside the AMQP
  credentials — whether mTLS identity can *replace* username/password AMQP
  auth depends on broker SASL ads (`EXTERNAL` vs `PLAIN`); see "mTLS vs.
  AMQP-level auth" (decided: negotiate from broker ads, never assume
  mTLS ⇒ passwordless)
- Hostname verification behavior should be explicit and overridable (useful
  for cluster/internal DNS setups) rather than silently permissive
- This is a natural target for **Phase 1 Lean proofs too**: the handshake
  state machine (TCP connect → TLS handshake incl. client cert exchange →
  AMQP `start`/`start-ok`/...) should be modeled as a single state machine
  so we can prove the AMQP handshake never proceeds on an unverified/failed
  TLS handshake — i.e. no state transition into AMQP protocol negotiation
  is reachable except through a completed, verified TLS handshake when TLS
  is configured

This is the layer most amenable to conventional fuzzing/property-based
testing (round-trip encode/decode, malformed-frame handling) in addition to
any Lean-level treatment. It's also the primary throughput-sensitive layer —
frame encode/decode and socket I/O sit directly in the hot path, so
allocation and copying here should be benchmarked deliberately rather than
assumed acceptable (e.g. zero-copy/`memoryview`-based framing where
practical, avoiding per-frame allocation churn under sustained publish/
consume load).

## Layer 2: Protocol (AMQP state machine)

Responsibility: legal AMQP behavior — the state machine a compliant client
must follow.

- **Connection state machine**: `start` → `start-ok` → `tune` → `tune-ok` →
  `open` → `open-ok` → ... → `close`/`close-ok`.   `start`/`start-ok` is also
  where SASL mechanism negotiation happens — the broker advertises its
  supported mechanisms (e.g. `PLAIN`, and `EXTERNAL` if the broker has the
  SSL auth plugin enabled) and the client must select from what's actually
  offered, not assume a mechanism is available. This is where the
  mTLS-as-auth question from the Transport layer resolves at runtime — see
  "mTLS vs. AMQP-level auth" (decided).
- **Channel state machine**: per-channel open/close, flow control
  (`channel.flow`)
- **Operations**: `exchange.declare`, `queue.declare`, `queue.bind`,
  `basic.publish`, `basic.consume`, `basic.ack`/`basic.nack`,
  `basic.qos` (prefetch)
- Heartbeat handling

This layer is the **first target for Lean proofs** (Phase 1 from the intent
doc): model connection/channel states as an explicit state machine and prove
things like "no method is sent in a state where the broker would reject it
per the AMQP spec" and "close is always reachable / no state is a dead end."

## Layer 3: Session

Responsibility: turn raw AMQP operations into the building blocks the pattern
layer needs — this is where "send a request and get the matching reply back"
becomes possible.

- **Correlation table**: outstanding request id → `asyncio.Future`, fed by a
  **per-connection exclusive, auto-delete reply queue** consumed continuously
  from connect to disconnect (see "Reply routing" below for the decision and
  rationale). The id is
  generated once at the Session layer and carried in **both** the JSON-RPC
  2.0 `id` field (body) and the AMQP `correlation_id` message property
  (transport), always kept identical between the two — not independently
  set. The client API exposes both as distinct accessors (AMQP
  `correlation_id`, JSON-RPC `id`) for AMQP-level tooling/tracing
  compatibility, even though they reference the same value.
  **Format: most restrictive side adopted.** AMQP's `correlation_id`
  property is a `shortstr` — at most 255 **octets** (byte length, not
  character count — matters once non-ASCII text is possible). The id format
  for this library is therefore a **string, ≤255 octets UTF-8-encoded**, and
  in practice restricted further to a safe ASCII subset (UUID4 hex, 32
  chars, as the default/recommended form) so octet-count and
  character-count never diverge. Never a number or `null`, even though
  JSON-RPC 2.0 permits those. This is enforced by a single validation
  function at the Session layer, applied to both library-generated ids and
  any caller-supplied id (e.g. for idempotency/tracing) — reject invalid
  ids rather than truncate or coerce — and reflected consistently in public
  documentation and example code, not left as an internal detail a consumer
  only discovers via a validation error.
- **Caller-supplied id collision — decided.** The correlation table's id
  space is connection-scoped. If a single connection/session is shared
  across multiple logical callers (e.g. a service forwarding requests from
  many upstream users over one mesh connection), caller-supplied ids
  (permitted for idempotency/tracing) are an injection surface: a caller
  could deliberately choose an id colliding with another concurrent
  request's id on the same connection to intercept its reply, since the
  resolution rule is "first reply for a given id wins."
  **Invariant (SpeC++/Lean):** a caller-supplied id must not collide with
  any id currently outstanding in the same correlation table; the Session
  layer **rejects the request outright** on collision rather than silently
  regenerating a fresh id. Library-generated ids (UUID4 hex) are produced
  only after confirming non-collision (astronomically unlikely; still
  checked). This sits alongside the existing id-format and id-consistency
  invariants.
- **Timeout / cancellation** of pending requests
- **Reconnect coordination**: on connection loss, what happens to
  in-flight requests, consumers, and mesh bindings — this is where a lot of
  the interesting correctness properties live (Phase 2 of the Lean work)

This is also the natural layer for the **second Lean proof target**: "every
request either resolves its future with a matching reply, an error, or a
timeout — never silently drops it," "correlation ids are never reused
while a request is outstanding," "the AMQP `correlation_id` property and the
JSON-RPC `id` in the body are always identical for a given message, never
independently generated or allowed to diverge," and "every id accepted by
the Session layer satisfies the format constraint (string, ≤255 octets) —
no id enters the correlation table unvalidated."

## Layer 4: Pattern (nuropb parity, JSON-RPC 2.0 vocabulary)

Responsibility: the actual messaging patterns applications use.

- **RPC request/reply** — envelope shaped like JSON-RPC 2.0:
  ```json
  {"jsonrpc": "2.0", "method": "service.method", "params": {...}, "id": "..."}
  {"jsonrpc": "2.0", "result": {...}, "id": "..."}
  {"jsonrpc": "2.0", "error": {"code": ..., "message": ..., "data": ...}, "id": "..."}
  ```
  mapped onto a per-connection exclusive auto-delete reply queue for
  the response leg (see Reply routing decision).
- **Notifications / pub-sub** — JSON-RPC "request without `id`" shape,
  mapped onto AMQP topic/fanout exchanges instead of a reply queue.
- **Mesh registration/binding** — service announces itself, binds its
  `service.method` routing keys; no direct JSON-RPC equivalent, stays
  nuropb-inspired.
- **Context/claims propagation** — carried in **AMQP message headers/
  properties**, not inside the JSON-RPC envelope. **Decided**: since the
  purpose of adopting JSON-RPC 2.0 is interoperability with MCP/A2A tooling,
  the JSON-RPC body must stay spec-pure and parseable by a stock JSON-RPC/MCP
  client — nuropb-specific extensions like context/claims don't belong inside
  `params` or as sibling keys on the envelope. They travel instead as AMQP
  message headers (the `headers` table in the AMQP `basic.properties`), kept
  fully separate from the JSON-RPC body. Still to be scoped: the specific
  header schema/naming and how claims get serialized into headers.

This separation is deliberate: MCP/A2A tooling and other stock JSON-RPC
clients only ever need to see a spec-pure `{"jsonrpc": "2.0", ...}` body to
interoperate — nuropb-specific concerns (context/claims, and potentially other
mesh-only metadata) stay entirely in the AMQP transport envelope, never
leaking into the JSON-RPC payload itself.

**Claims integrity, replay, and fail-closed — decided.**

Threat → mechanism → library vs deployment:

| Threat | Mechanism |
|---|---|
| Headers swapped onto a different JSON-RPC body | Signed JWT whose claims include the authorized `method` (and optionally a hash of canonicalized `params` when the issuer supports it); verification fails if method (and params hash, if present) do not match the body |
| Captured token replayed on another request | JWT `exp` required (short-lived); JWT `jti` must equal the message correlation id (or a library-defined claim that is byte-identical to it) so a token is bound to one request id |
| Missing/malformed claims on an auth-required method | **Fail-closed**: reject; never treat as anonymous/default-permission |
| Timing oracle on token compare | Constant-time comparison of signature/MAC material (`hmac.compare_digest` or equivalent) |

**Token model (v1):** signed JWT bearer carried in AMQP headers (nuropb-like). Issuance and revocation remain an upstream IdP concern (`project-intent.md` trust boundary); the library propagates, verifies signature against configured trust roots, checks `exp` / `jti`↔correlation-id / method binding, and invokes application `authorize_func`-style hooks only after those checks succeed.

**Fail-closed default:** a method that requires authorization has **no** code path that skips claims validation, including missing or malformed headers. Methods that are explicitly configured as public may omit claims; that configuration is named and validated in the pattern profile, not inferred from absence of headers.

**SpeC++/Lean invariants (Pattern):**
- Auth-required method ⇒ valid verified JWT bound to this request, or reject.
- Verified JWT's `jti` equals the message correlation id.
- Verified JWT's `method` claim equals the JSON-RPC `method`.
- Missing/malformed/expired/unbound token ⇒ unauthorized error (never success).

**Header schema** (wire names; all under AMQP `basic.properties.headers`):

| Header key | Type | Meaning |
|---|---|---|
| `nr.claims` | `longstr` | Compact JWT serialization (JWS compact) |
| `nr.claims_typ` | `shortstr` | Always `JWT` in v1 (rejects unknown types) |

No claims material is placed in the JSON-RPC body. Additional mesh metadata headers use the `nr.` prefix and are enumerated in "SpeC++ prep artifacts" below as they are added — never ad-hoc sibling keys on the JSON-RPC envelope.

**Mesh registration authorization — decided (broker-native v1).**

Threat: an unauthorized process binds to an existing `service.method` routing key and intercepts or answers requests (mesh hijack).

| Role | Responsibility |
|---|---|
| RabbitMQ / deployment | Hard gate: vhost users may only `bind`/`consume` on routing keys (or topic patterns) for service namespaces they own; write to other services' request exchanges is denied |
| Library | Documents the **mesh-binding permission profile**; declares queues/bindings only for the configured service identity; refuses to bind outside the configured namespace (client-side guardrail, not a substitute for broker ACL) |
| App-level registration authority | **Done as discovery aid only** — optional announce/viewer on `nr.mesh.registry`; never a replacement for broker permissions or `assert_bind_allowed` |

**SpeC++/Lean invariant (Pattern, client-side):** mesh bind operations are only issued for routing keys within the connection's configured service namespace; unauthorized bind is a broker rejection (external) and/or a client-side refuse-before-send.

This matches the trust boundary: AMQP authorization is a deployment prerequisite; Lean does not prove broker ACL correctness.

## Failure modes: service-side request handling

This section specifies the failure-handling design for the *service* (request
consumer) side of the RPC pattern — how requests survive service failures,
how stuck messages are bounded, and how the client eventually learns a
request timed out even if no service instance ever answers.

**Normal path:**
1. Service consumes from a **durable** request queue, manual ack
   (`auto_ack=False`).
2. Request is fully processed and the response is published to the request's
   `reply_to` queue (the per-connection exclusive queue from the "Reply
   routing" decision above) with the matching `correlation_id`.
3. **Only after** the response publish completes does the service ack the
   original request.

**Failure path — service instance dies:**
4. If the service instance crashes or disconnects before acking, RabbitMQ
   requeues the unacked message for redelivery to any other active consumer
   on the same queue — a sibling instance of the same service (standard
   AMQP competing-consumers / work-queue pattern; this is the same
   queue/binding the mesh registration pattern already sets up).
5. **Accepted consequence: at-least-once processing, not exactly-once.** If
   the crash happens *after* the response was published but *before* the ack
   is durably recorded, redelivery causes a sibling to reprocess the request
   and send a **second** response. This is a deliberate trade-off, not a
   bug to eliminate — see "Duplicate response handling" below for why it's
   safe to accept.

**Failure path — message never successfully processed:**
6. A message that keeps bouncing between failing/dying instances (or is
   simply never picked up) is bounded by **message TTL**: once its TTL
   expires, RabbitMQ dead-letters it to a DLQ (requires
   `x-dead-letter-exchange`, and optionally `x-dead-letter-routing-key`,
   configured on the main request queue). RabbitMQ preserves the original
   message's properties/headers through dead-lettering and adds an
   `x-death` header recording cause/queue/count — the DLQ processor should
   use this to confirm the reason is TTL expiry (as opposed to some other
   use of the same DLX, if one exists) before synthesizing a timeout.
7. A dedicated **DLQ processor** consumes from the dead-letter queue and, for
   each dead-lettered message, synthesizes a JSON-RPC 2.0 error response
   (using the nuropb-specific error code block, `-33000..-33999`, decided
   under "Error code mapping" above — a timeout is not a JSON-RPC
   protocol-level error) and publishes it to the original message's
   `reply_to`, using the original `correlation_id`.
8. This reuses the **exact same reply mechanism** as a normal RPC response —
   no new wire format, no new client-side handling path. The client Session
   layer doesn't need to know the DLQ/timeout-synthesis path exists at all:
   a real reply, a DLQ-synthesized timeout error, and the client's own local
   per-request timeout are simply three things racing to resolve the same
   pending future. Whichever arrives first wins.
9. If `reply_to` is no longer routable when the DLQ processor publishes (the
   client's connection died, so its exclusive reply queue was auto-deleted
   per the earlier decision), the message is dropped — accepted as
   specified. The DLQ processor should publish with **`mandatory=true`** so
   an unroutable drop produces a `basic.return` the processor can log/count,
   giving observability into true drops without changing the drop outcome.

**Duplicate response handling.** A duplicate response (from step 5) and a
late DLQ timeout arriving after local timeout (from step 8) are the same
class of event from the client's point of view: *a message referencing a
correlation id that is no longer pending.* The client's correlation table
already needs a rule for this — **first reply for a given id resolves the
pending future; any later message with the same id is discarded silently,
not treated as an error** — and that single rule absorbs both cases without
special-casing either one.

**Reply forgery — decided (permission profile).** The "first reply for a
given id resolves the pending future, later messages discarded" rule is
designed against *legitimate* duplication (crash-then-redelivery, DLQ
timeout racing a real reply) but does not by itself distinguish a
legitimate reply from a forged one: any AMQP publisher able to write to a
client's reply queue with the right `correlation_id` can pre-empt the
genuine response. Close this at the permission layer, not the Session
logic layer:

- **Mechanism:** RabbitMQ vhost/user authorization (configure write
  permission on the reply-queue name pattern so only identities that should
  answer RPC — typically service accounts bound to the request exchange —
  can publish to a given client's exclusive reply queue). Prefer naming
  reply queues with a library-owned prefix (e.g. `nr.reply.<connection-id>`)
  so ACL topic/resource patterns can target them without listing every
  queue.
- **Library role:** documents the required permission profile as a
  **deployment prerequisite**; may offer a connection-setup helper that
  *declares* the reply queue and *asserts* (via a documented checklist /
  optional management-API check in ops tooling) that the profile is in
  place — it does **not** attempt to replace broker ACL with
  application-level reply authentication in v1.
- **Trust boundary:** Session-layer Lean proofs assume replies arrive only
  from brokers-authorized publishers; that assumption is enforced by
  RabbitMQ configuration, not by the proofs themselves (same framing as
  `project-intent.md` trust boundary).
- **SpeC++ invariant (client-side):** first-reply-wins + discard-later holds
  for any well-formed reply frame accepted from the reply consumer; the
  permission profile is an external axiom, not a client-proved property.

**Lean Phase 2 invariants (proved — SpeC++ + Lean DeadLetterTimeout/Reconnect):**
- Every request that enters the request queue eventually reaches exactly one
  of two terminal states: acked-with-response-sent by some service instance,
  or dead-lettered-and-timeout-synthesized — bounded by TTL, so no request
  can loop in the request queue forever without eventually terminating.
- The correlation table's "first reply wins, later messages for a resolved
  id are discarded" rule holds regardless of which of {real reply, real
  duplicate reply, DLQ-synthesized timeout} arrives second.
- A response that fails to route to its `reply_to` does not corrupt the
  state of any other in-flight request (isolation).
- **Mutual exclusivity of DLQ-timeout and legitimate processing:** for a
  given delivery, "dead-lettered due to TTL expiry" and "successfully
  processed by a service instance" are mutually exclusive outcomes — never
  both. This is the formal statement of the correctness property motivating
  "broker-side TTL as authoritative" below, and is a natural target once
  the Protocol layer's Ready/unacked state distinction is modeled.

**Decided:**
- **Broker-side TTL/DLQ (and `consumer_timeout`) is the authoritative
  timeout mechanism when the broker provides it, as RabbitMQ does.
  Client-side local timeout is a fallback, not a default parallel
  mechanism.** This resolves a real correctness concern, not just a style
  preference: a client-side wall-clock timer has no visibility into whether
  a service instance has actually begun processing a request, so it can
  fire while the request is legitimately, correctly still in flight —
  producing exactly the hazard of the client unilaterally declaring failure
  locally while a genuine success response is still on its way, arriving
  after the client (and whatever discarded the "failed" outcome to) has
  already moved on. That's a real ordering/guarantee violation, not merely
  an annoyance: a side effect the caller believes never happened may in
  fact have completed.
  - **Why the broker-side path avoids this structurally, not just
    empirically.** RabbitMQ message TTL applies only to messages in the
    *Ready* (unconsumed) state — a message already delivered to and being
    processed by a consumer will not expire while unacked, specifically
    because the consumer might still be legitimately working on it. This
    means "TTL-expired → dead-lettered → synthesized timeout" and "a
    service instance is correctly mid-flight on this request" are mutually
    exclusive outcomes for the same delivery: the broker's timeout signal
    is conditioned on the message never having been successfully picked up
    and worked, not merely on elapsed time. A client-side timer has no such
    guarantee.
  - **The remaining gap — a consumer that hangs without crashing** (holds a
    message unacked indefinitely due to an application-level stall, not a
    process death) — is also covered broker-side by RabbitMQ's
    `consumer_timeout`: the broker force-closes the channel once a
    delivery goes unacked past that timeout, requeuing the message back to
    Ready state, where it becomes TTL-eligible again. Between message TTL
    and `consumer_timeout`, RabbitMQ's native toolkit already covers
    essentially the full space of "stuck" scenarios without the client
    needing an independent wall-clock guess.
  - **Client-side local timeout's role, narrowed accordingly:** it is
    engaged only when connecting to a broker or deployment that does not
    provide message TTL + DLX + `consumer_timeout` capability (broker
    capability becomes something to detect/configure at connect time — see
    "Configuration Strategy" above) — not run by default as a race against
    RabbitMQ's own mechanism. When it is engaged as a fallback, it should
    be deliberately generous rather than tuned to "typical" latency, since
    without broker coordination it has no way to distinguish "still
    legitimately processing" from "stuck," and erring toward a late
    fallback failure is safer than erring toward the false-positive this
    decision is specifically meant to avoid.
  - **Caveat, for completeness.** RabbitMQ documents a narrow internal race
    at the exact instant of expiry — a message can expire after being
    written to the socket but before reaching a consumer. This is a
    RabbitMQ-internal timing detail, not a client/broker disagreement about
    outcome: in that instant the message was never actually processed, so
    the DLQ timeout outcome is still the correct one — it doesn't reopen
    the ordering hazard this decision addresses.
  - **The duplicate-response handling from the failure-modes section above
    is still necessary regardless** (a crash between response-send and ack
    still produces a legitimate duplicate) — but it's no longer also
    covering for a client/broker disagreement about whether a request
    timed out at all, since that specific race is structurally avoided
    when broker capability is present.

**Poison-message / durability — decided via default profile.** Pure TTL
bounds *time*, not attempt count. The default named profile
`durable-at-least-once` therefore uses **quorum queues + `x-delivery-limit`
+ TTL + DLX + persistent messages** together (see Configuration Strategy).
Classic/TTL-only remains available as an explicit non-default profile for
deployments that accept the poison-message DoS trade-off.

## Configuration Strategy

Several of the decisions above introduce configuration knobs that are easy
to set independently and easy to leave silently mismatched — durability is
the clearest example (a `durable=True` queue with non-persistent messages
looks correctly configured and only fails to protect data at the worst
possible moment: a broker restart). Rather than documenting each knob as a
"remember to also set X" footnote, these are treated as a single,
structural configuration concern.

**Approach:**

1. **Config is a validated object, not scattered kwargs.** Durability-
   relevant settings (queue `durable`, message `delivery_mode`, TTL,
   dead-letter exchange/routing key, classic vs. quorum queue type,
   redelivery limit) are expressed as one queue/connection configuration
   profile, not independently passed at each call site. The profile is
   validated as a unit — not each field validated in isolation — so
   internally inconsistent combinations are caught at configuration time.
2. **Linked settings are enforced together, not just documented together.**
   Concretely for durability: if a queue profile declares `durable=True`,
   the publish path for that queue refuses (raises, doesn't warn-and-
   proceed) to send a non-persistent (`delivery_mode=1`) message — the same
   "reject rather than silently accept a bad combination" pattern already
   used for correlation id format validation. The inverse (non-durable queue
   with persistent messages) is legal but should be flagged, since it's
   very likely not what was intended.
3. **Sensible, named defaults, not silent ones.** Ship named configuration
   profiles covering the common cases; the default without an explicit
   choice is `durable-at-least-once`.
4. **This is itself SpeC++/Lean territory.** "A queue declared durable and
   its published messages' persistence never disagree" belongs in the
   SMT-consistency-checked spec layer.
5. **Poison-message bound is a profile concern.** TTL bounds *time*,
   `x-delivery-limit` bounds *attempt count* (quorum only). Profile
   validation enforces that dependency at config time.
6. **Permission profiles** (deployment prerequisites, documented here and
   enforced by RabbitMQ; library documents + optional ops checks):
   - **Reply-queue publish restriction** — see "Reply forgery" above.
   - **Mesh-binding namespace authorization** — see "Mesh registration
     authorization" above.

### Named profiles (v1 draft)

**Queue / delivery profiles**

| Profile name | Queue type | durable | delivery_mode | TTL+DLX | x-delivery-limit | Notes |
|---|---|---|---|---|---|---|
| `durable-at-least-once` (**default**) | quorum | yes | 2 (persistent) | required | required | Poison-message DoS mitigated |
| `durable-classic` | classic | yes | 2 | required | forbidden | Explicit opt-in; TTL-only poison bound |
| `transient-fast-path` | classic | no | 1 | optional | forbidden | Lossy; never silent default |

**TLS / hostname profiles** (no silent `verify_hostname=False` bool)

| Profile name | Behavior |
|---|---|
| `tls-verify-full` (**default**) | Verify cert chain + hostname against configured SANs/DNS |
| `tls-verify-custom-san` | Verify chain; hostname match against an explicit allowlist of names (cluster/internal DNS) — loud, named, never “off” |
| `tls-insecure-dev-only` | No hostname/chain verify — **rejected outside explicitly marked development builds**; not a production-selectable default |

**Permission profiles** (broker-side; library documents required shape)

| Profile | Requirement |
|---|---|
| `reply-publish-restricted` | Only authorized service identities may write to `nr.reply.*` (or configured reply-queue prefix) |
| `mesh-bind-namespaced` | Bind/consume limited to the identity’s `service.*` routing-key namespace |

**Cert rotation — decided.** Secrets-manager hooks are re-invoked on **each
new TCP/TLS connection**. Mid-connection cert expiry does not hot-swap the
TLS context in place; the library performs an orderly reconnect using freshly
loaded material. Key bytes must never appear in logs, `repr`, or exception
messages.

## Package layout

```
src/<pkg>/
  transport/
    frame.py          # AMQP frame encode/decode
    connection.py      # TCP + TLS socket handling
  protocol/
    connection_sm.py   # connection state machine
    channel_sm.py       # channel state machine
    methods.py           # AMQP method (de)serialization
  session/
    correlation.py      # id -> future tracking
    reconnect.py          # reconnect/rebind coordination
  patterns/
    rpc.py                 # JSON-RPC 2.0 request/reply over AMQP
    events.py                # JSON-RPC notification-shaped pub/sub
    mesh.py                    # registration/binding
    context.py                   # claims/context propagation
    dlq_timeout.py                 # DLQ consumer: synthesizes timeout
                                    # error replies (see "Failure modes:
                                    # service-side request handling" above)
  api.py                          # public, nuropb-inspired but new API surface
specs/                              # Lean project
  Protocol/ConnectionSM.lean
  Protocol/ChannelSM.lean
  Session/Correlation.lean
  Session/DeadLetterTimeout.lean  # Phase 2: terminal-state / TTL-bound proof
tests/
```

## Sequencing proposal

1. **Transport + Protocol layers** — **DONE.** Native connection to RabbitMQ,
   open a channel, declare a queue, publish/consume/ack a raw message in
   `src/nuropb_rmq/` (no `pika`). SpeC++ Protocol SM CheckSat passed under
   `specs/specpp/`.
2. **Lean Phase 1** — **DONE.** Connection/channel state machine modeled and
   invariants 1–7 proved under `specs/lean/` (`lake build`); hypothesis PBTs
   and `CORRESPONDENCE.md` keep Python aligned.
3. **Session layer + RPC pattern** — **DONE.** Correlation table, exclusive
   reply queue, JSON-RPC 2.0 request/reply (`RpcClient`/`RpcServer`), DLQ
   timeout synthesis; unit + integration smoke under `tests/`.
4. **Lean Phase 1b** — **DONE.** Session correlation invariants proved
   (`NuropbRmq.Session`); SpeC++ Session CheckSat sat/unsat; PBTs under
   `tests/session/`.
5. **Events/pub-sub pattern** — **DONE.** JSON-RPC notification shape over
   topic/fanout (`EventPublisher` / `EventSubscriber`); unit + integration smoke.
6. **Mesh registration/binding + context/claims** — **DONE.** `MeshService` /
   `ServiceIdentity` namespaced binds; JWT claims in `nr.claims` headers via
   optional `[claims]` extra; wired into `RpcClient`/`RpcServer`; SpeC++ Pattern
   CheckSat.
7. **Lean Phase 2 / reconnect** — **DONE.** Fail-fast `CONNECTION_LOST` on
   disconnect; `Session.reconnect` / `ReconnectCoordinator`; `MeshService.rebind`;
   SpeC++ Phase 2 CheckSat; Lean `DeadLetterTimeout` + `Reconnect` proofs.

**v1 core sequencing complete.** Release CI, Pattern Lean, AMQPS verify-full,
mTLS EXTERNAL, PEM + PKCS#12 cert sourcing, named queue profiles, heartbeat
watchdog, and optional mesh discovery registry are in place. Remaining deferred
item: in-flight park-and-retry.

**Throughput:** `bench/` compares nuropb-rmq vs pika for raw publish/consume,
RPC exclusive reply queue, pika `amq.rabbitmq.reply-to`, and fanout events.
`pika` is only an optional `[bench]` dependency — never a runtime requirement.
Exclusive reply-queue remains the product default; direct reply-to is a
measured baseline only.

## Decisions log (detail)

Formerly “Open questions.” Items below are decided unless marked deferred.
Cross-check the Decision ledger at the top of this document for status.

- **Correlation id placement — decided.** The AMQP `correlation_id` message
  property and the JSON-RPC 2.0 `id` field carry the **same underlying
  value**, generated once at the Session layer, and are exposed to the client
  API as two distinct accessors (AMQP `correlation_id`, JSON-RPC `id`) rather
  than collapsed into one. This is deliberate: the AMQP `correlation_id`
  property is what makes reply-routing and AMQP-level tracing/debugging work
  for participants that never parse the JSON-RPC body (brokers, management
  tooling, other non-nuropb AMQP clients on the mesh) — collapsing to the
  JSON-RPC `id` alone would silently require every such participant to
  understand JSON-RPC just to do basic correlation, undermining AMQP-level
  interoperability. Consequences:
  - **Format — most restrictive side adopted.** AMQP's `correlation_id` is a
    `shortstr`: at most 255 **octets** (byte length, not character count).
    Since the two fields must carry an identical value, the id format for
    this library is a **string, ≤255 octets UTF-8-encoded** — never a bare
    number or `null`, even though JSON-RPC 2.0 permits those — and in
    practice restricted to a safe ASCII subset (UUID4 hex, 32 chars, as the
    default) so octet-count and character-count can't diverge. This is a
    project-level constraint on top of the JSON-RPC spec, not a spec
    violation.
  - **Enforced, not just documented.** A single validation function at the
    Session layer checks every id — library-generated or caller-supplied —
    against this format before it's used, rejecting invalid ids rather than
    truncating or coercing them. Public documentation and example code
    consistently show ids in this form so the constraint is visible
    up-front, not discovered via a validation error.
  - This yields a new invariant for the Session-layer Lean proof: the AMQP
    `correlation_id` property and the JSON-RPC `id` in the body must never be
    allowed to diverge for a given message — both are derived from a single
    id generated once at the Session layer, not independently set — and
    every id in the correlation table satisfies the format constraint.
- **Reply routing — decided.** Per-connection **exclusive, auto-delete reply
  queue** (Option B), not RabbitMQ's `amq.rabbitmq.reply-to` fast-path
  (Option A). One real (exclusive, auto-delete) queue is declared per
  connection at connect time, consumed from continuously, with replies
  multiplexed by correlation id the same way either option would do it.
  Rationale:
  - **Provability.** A real queue gives message durability-within-the-queue:
    a reply published while the consumer is momentarily busy sits in the
    queue rather than being dropped. This makes "every outstanding request
    gets exactly one reply or a well-defined timeout/error" provable under
    normal AMQP delivery semantics without an extra liveness precondition on
    the consumer's exact timing — direct reply-to's fast path has no backing
    store and silently drops a reply if the requester isn't consuming at the
    exact instant of delivery, which would have required the Session layer
    to enforce and the Lean proof to assume a continuous-consumption
    invariant. The exclusive queue avoids needing that assumption at all.
  - **Robustness.** A real queue is more forgiving of transient consumer
    stalls — the failure mode under normal operation is cleaner, with no
    forced auto-ack and no per-message drop risk.
  - **Trade-off accepted.** This is a deliberate choice against raw
    throughput: real queue declare/bookkeeping is measurably more broker
    overhead than the reply-to fast path. Per the project's stated
    trust/robustness/throughput goals, this is the trust-and-robustness
    side of that trade-off, made explicitly rather than left implicit — the
    actual throughput cost should still be measured (see "Throughput
    benchmarking" below) so the trade-off's size is known, not just its
    direction.
  - **Still connection-scoped.** Exclusive/auto-delete queues die with the
    connection regardless of which option was chosen; reconnect recreates the
    reply queue on a new connection epoch (Phase 2 — **done**).
  - **Session layer consequence:** the reply queue is declared once at
    connect and torn down only at disconnect — never toggled per-request —
    so its lifetime cleanly brackets the correlation table's lifetime,
    which is itself a useful Session-layer invariant for the Lean proof
    ("the reply queue is open for the entire interval in which any request
    is outstanding").
- **Lean-to-Python coupling — decided (v1).** Pipeline:
  1. Formalize invariants as SpeC++ clauses; pass `CheckSat`.
  2. Model the same invariants in Lean (Protocol/Session first).
  3. Keep Python aligned via **property-based tests derived from the Lean
     model** plus **manual correspondence review** between Lean defs and
     Python modules.
  Code extraction / generated implementation is **out of scope for v1**.
- **Specification/invariant consistency — decided.** Independent of how Lean
  proofs couple to the Python implementation, the specs and invariants
  themselves (Protocol layer state machine, Session layer correlation
  invariants, id-format constraint, error-code namespace separation, etc.)
  must be checked for internal consistency against an SMT solver — **Z3 or
  CVC5** — via the **SpeC++** workflow before being treated as settled. This
  is a distinct, prior gate to the Lean proof work: SpeC++'s pipeline
  formalizes each normative requirement as a clause over a declared sort
  universe and runs a mandatory `CheckSat` step after every repair cycle —
  a clause set that is contradictory (UNSAT) or that the solver can't
  resolve (UNKNOWN) blocks approval outright, with no waiver. Concretely for
  this project:
  - Each pattern's invariants (e.g. the Session layer's "every request
    resolves to exactly one of {reply, error, timeout}," the correlation id
    format/consistency invariants, the mesh registration/binding rules) get
    lifted into SpeC++ clauses with an explicit sort universe before being
    handed off for Lean proof work — SMT consistency-checking the
    *specification* first, Lean proving the *implementation* satisfies it
    second.
  - A specification that fails `CheckSat` (i.e. is self-contradictory) must
    be repaired and re-checked before any Lean proof effort is spent on it —
    no point formally proving code correct against a spec that can't
    itself be satisfied.
  - This gives the project two layers of formal assurance: SMT-checked
    consistency of the specs themselves, and Lean-proved correspondence of
    the implementation to those specs. Both serve the "trust" project goal,
    at different points in the pipeline.
- **Error code mapping — decided.** JSON-RPC 2.0's full reserved block is
  `-32768` to `-32000` (not just the five named codes); within it, `-32000`
  to `-32099` is explicitly earmarked by the spec as "reserved for
  implementation-defined server-errors," and codes outside `-32768..-32000`
  entirely are open for application use. Convention:
  - `-32000..-32099` used sparingly — at most a couple of generic coarse
    fallback codes.
  - Nuropb application/pattern taxonomy lives in `-33000..-33999` (see
    SpeC++ prep artifacts for the enumerated categories).
  - `error.data` is allowlisted (see below); validated at construction.
- **`error.data` allowlist — decided.** Permitted keys only:
  `code_name` (stable string id), `retryable` (bool), `correlation_id`
  (echo), `method` (echo). Forbidden in any response that may cross a trust
  boundary: stack traces, exception types/messages verbatim, hostnames,
  queue/exchange names, raw `x-death` / broker headers, filesystem paths,
  cert material. DLQ-synthesized timeouts use the same public shape as other
  timeout errors (supports the anti-enumeration goal below).
- **TTL anti-enumeration — decided (goal).** Across the public mesh API,
  callers must not be able to distinguish “method does not exist / not
  bound” from “method exists but timed out” via response content or
  statistically reliable timing alone. Implementation obligation: same
  error code/message family for both; avoid leaking registration state in
  `error.data`.
- **mTLS vs. AMQP-level auth — agreed.** Whether a verified client
  certificate can stand in for AMQP username/password is not purely our
  design choice — it depends on what SASL mechanisms the target RabbitMQ
  broker supports and has enabled via AMQP 0-9-1's
  `connection.start`/`start-ok` negotiation. RabbitMQ can be configured to
  offer the `EXTERNAL` SASL mechanism (via the `rabbitmq_auth_mechanism_ssl`
  plugin), in which case a verified client cert *can* satisfy authentication
  with no username/password exchanged; if that plugin/mechanism isn't
  enabled on the broker, only `PLAIN` (or whatever mechanisms the broker
  advertises) is available and username/password is required regardless of
  mTLS. Accordingly, the library:
  - negotiates SASL mechanism from whatever the broker actually advertises in
    `connection.start`, rather than assuming `EXTERNAL` is available
  - supports `EXTERNAL` as one mechanism option when the broker offers it,
    with `PLAIN` (or others) as fallback/alternative
  - never hardcodes an assumption that mTLS implies passwordless auth —
    that's a broker-side configuration outcome, not a client-side guarantee
- **Reply-queue publish authorization — decided.** Broker-native RabbitMQ
  permission profile (`reply-publish-restricted`); library documents as
  deployment prerequisite and may assist with ops checks; no application-
  level reply authentication in v1. Detail under "Reply forgery."
- **Mesh-binding authorization — decided.** Broker-native namespaced
  permissions (`mesh-bind-namespaced`); library refuses binds outside
  configured service namespace. Optional discovery registry
  (`patterns/registry.py`) never gates bind. Detail under "Mesh registration
  authorization."
- **Cert/key material sourcing — done (PEM + PKCS#12).** All sources normalize
  to `TlsMaterial` PEM slots (`src/nuropb_rmq/transport/tls_material.py`):
  - **File paths** — PEM cert and key files on disk, the common case
    for local dev and simple container deployments (e.g. mounted secrets).
  - **In-memory bytes** — cert/key supplied directly as bytes/`str`, for
    callers who've already loaded material some other way (e.g. from an
    environment-injected value, or already fetched from elsewhere) and don't
    want a round-trip through the filesystem.
  - **PKCS#12** — `pkcs12_file` / `pkcs12_data` (+ optional password); soft-imports
    `cryptography` via optional `[pkcs12]` extra; mutually exclusive with PEM
    cert/key slots.
  - **Secrets-manager hook** — a pluggable provider interface (e.g. an
    async callable returning `TlsMaterial`, or an object with
    `get_tls_material()`) so integrators can back it with Vault, AWS/GCP/Azure
    secrets managers, or any internal system, including support for **rotation**
    (re-invoke on each new connection; mid-connection expiry → orderly
    reconnect — see Configuration Strategy).
  - All three normalize to the same internal representation before being
    handed to the TLS layer, so the Protocol/Transport layers don't need to
    know which source was used — the difference is confined to a small
    loader abstraction at the config/connection-setup boundary.
  - Validation (matching cert/key pairs via `load_cert_chain`, CA via
    `cadata`/`load_verify_locations`) runs the same way regardless of source,
    so a bad secrets-manager response fails the same clear way a bad file
    path would, rather than surfacing as an opaque TLS handshake failure later.
  - Private key material never appears in logs, `repr`, or exception
    messages.
- **Throughput benchmarking — done.** Harness under [`bench/`](../bench/);
  install `pip install -e ".[bench]"` (pulls `pika` for comparisons only).
  Run `python -m bench.compare` (or `--quick`). Workloads: raw
  publish/consume, RPC exclusive reply queue (both libraries), pika-only
  `amq.rabbitmq.reply-to`, fanout notifications (N=1 and N=3). Reports
  msgs/sec and latency p50/p99 to `bench/results/*.json`. Exclusive
  reply-queue remains the product default; direct reply-to is measured,
  not reopened as the default path.

## SpeC++ prep artifacts

Protocol SM formalization is live under [`specs/specpp/`](../specs/specpp/).
Run `python specs/specpp/check_sat.py` (Z3). Positive model must be **sat**;
forced-violation negatives must be **unsat**. UNKNOWN is a hard failure.

### Error taxonomy (`-33000..-33999`)

| Range | Category | Example codes (stable names) |
|---|---|---|
| `-33000..-33099` | Validation / id format | `INVALID_ID`, `ID_COLLISION`, `INVALID_ENVELOPE` |
| `-33100..-33199` | Authorization / claims | `UNAUTHORIZED`, `CLAIMS_MISSING`, `CLAIMS_EXPIRED`, `CLAIMS_UNBOUND` |
| `-33200..-33299` | Mesh / routing | `SERVICE_UNAVAILABLE`, `BIND_REFUSED`, `UNROUTABLE` |
| `-33300..-33399` | Timeout / delivery | `REQUEST_TIMEOUT`, `CONSUMER_TIMEOUT` |
| `-33400..-33499` | Session / connection | `CONNECTION_LOST`, `CHANNEL_CLOSED`, `NOT_CONNECTED` |
| `-32000` | Shared coarse fallback only | `SERVER_ERROR` (use sparingly) |

Exact numeric assignments within each band are fixed at implementation time;
category bands and `code_name` strings are normative now.

### Claims header schema (recap)

- `nr.claims` (`longstr`): JWS compact JWT
- `nr.claims_typ` (`shortstr`): `JWT`
- Required JWT claims for auth-required methods: `exp`, `jti` (= correlation
  id), `method` (= JSON-RPC method). Optional: `params_sha256` when issuer
  supports body binding.

### Protocol connection/channel SM — SpeC++ invariant outline

**Status: CheckSat passed; Lean Phase 1 proofs in `specs/lean/`.** Sources:
`specs/specpp/Protocol/connection_channel_sm.smt2` and
`connection_channel_sm_negatives.smt2`. Lean theorems in
`specs/lean/NuropbRmq/Protocol/Invariants.lean`. Sort universe:
`ConnState`, `ChanState`, `Frame`, `TlsState`, `SaslMech`, `TlsProfile`,
`AmqpMethod`.

Consistency-check targets (Lean proves implementation afterward):

1. No AMQP method send is reachable except from a legal connection/channel
   state for that method (AMQP 0-9-1).
2. When TLS is configured: no transition into AMQP `start`/`start-ok`
   negotiation except through completed TLS handshake under the active TLS
   profile (including `tls-verify-custom-san`; `tls-insecure-dev-only` is a
   separately named, non-production profile).
3. SASL mechanism selection is only trusted when received over an
   already-verified TLS channel (when TLS is configured).
4. Every rejected state-machine transition results in channel and/or
   connection teardown — never a silent no-op that leaves client and broker
   views divergent.
5. Close is always reachable from any non-terminal state (no dead-end
   states).
6. Frame decode never allocates buffer space proportional to an unvalidated
   attacker-supplied length before checking against configured
   `frame_max` / body-size ceilings; field-table nesting depth is bounded.
7. Heartbeat timeout is a single profile-configured value (no parallel
   competing heartbeat policies).

Session-layer targets (Phase 1b) — **proved** in SpeC++ + Lean:

- Id format + dual-accessor consistency
- Caller-supplied id collision reject
- First-reply-wins / discard-later
- Reply-queue lifetime brackets correlation-table lifetime
