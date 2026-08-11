# Project Intent: Native Python RabbitMQ Service Mesh Library

## Summary

Build a new, Python-native RabbitMQ/AMQP client library, inspired by but not
bound to [nuropb](https://github.com/robertbetts/nuropb)'s API, that implements
the AMQP wire protocol directly (no `pika`, no third-party AMQP client
abstractions) and reproduces nuropb's full set of distributed service-mesh
messaging patterns on top of that native transport. Key patterns are to be
backed by Lean-proven correctness properties, not just tests.

## Background: nuropb

[nuropb](https://github.com/robertbetts/nuropb) ([docs](https://nuropb.readthedocs.io/en/latest/))
is a Python pattern/library for building a distributed, event-driven service
mesh on top of RabbitMQ. It targets use cases such as horizontally scaling
services, inter-service communication, event-driven flows, websocket-to-backend
bridging, REST-to-async proxying, deploying ML models as services, and
bridging cloud/on-prem networks. RabbitMQ was chosen by nuropb as the
underlying broker for its AMQP routing capabilities, low maintenance, and
robustness — any platform with RabbitMQ support can join the same mesh as
Python services.

nuropb's current implementation uses the `pika` async RabbitMQ client, wrapped
in nuropb's own abstraction layers. Its core patterns include:

- **RPC request/reply** — synchronous-style calls between services
  (`client_api.request(service=..., method=..., params=..., context=...)`)
- **Service mesh registration/binding** — services register and bind to the
  mesh (`RMQAPI`, `rpc_bindings`)
- **Event/pub-sub publishing** — event-driven flows across the mesh
- **Context/claims-based authorization propagation** — bearer-token-derived
  user claims passed through to method calls via a context manager
  (`NuropbContextManager`, `@publish_to_mesh(authorize_func=...)`)

## Motivation for this project

The current nuropb implementation has too much abstraction and too many
third-party dependencies layered around `pika`. This project exists to
implement native support for connecting to RabbitMQ directly — at the AMQP
protocol level — and to implement the nuropb messaging patterns on that native
foundation, with a leaner dependency footprint and less incidental
abstraction.

## Scope

**In scope for v1 — full pattern parity with nuropb:**

1. Native AMQP 0-9-1 protocol implementation (connection, channel, framing,
   handshake) — replacing `pika` entirely
2. TLS support, including mutual TLS (mTLS) — client certificate
   presentation and verification, not just server-certificate verification
3. RPC request/reply pattern
4. Event/pub-sub publishing pattern
5. Service mesh registration/binding pattern
6. Context/claims-based authorization propagation pattern

**API design:** A new, cleaner API — *not* a drop-in replacement for nuropb's
`RMQAPI`. The library should be nuropb-inspired at the pattern level, free to
depart from nuropb's exact interface.

**Messaging terminology: JSON-RPC 2.0.** The library's messaging vocabulary
and message envelope structure should adopt [JSON-RPC 2.0](https://www.jsonrpc.org/specification)
terminology and shape (`method`, `params`, `id`, `result`, `error`,
`jsonrpc: "2.0"`, notifications-as-requests-without-`id`, batch requests,
standard error object/codes) rather than nuropb's own naming, wherever the two
overlap. This is a deliberate interoperability choice: emerging agent/tool
protocols such as MCP (Model Context Protocol) and A2A (Agent2Agent) are
themselves built on JSON-RPC 2.0, so aligning this library's request/reply and
notification vocabulary with JSON-RPC 2.0 should make it easier to bridge or
integrate with those ecosystems later, rather than requiring a translation
layer between two different RPC vocabularies. This affects:

- The wire-level message envelope for the RPC request/reply pattern
- Error representation (JSON-RPC's `error` object/code conventions vs.
  nuropb's own error handling)
- Naming in the Python API surface (e.g., prefer `method`/`params`/`result`
  over any nuropb-specific naming)
- Possibly the event/pub-sub pattern, to the extent JSON-RPC notifications
  (a request object without an `id`) map onto it

Where nuropb's patterns have no JSON-RPC 2.0 equivalent (e.g., service mesh
registration/binding, context/claims propagation), those remain
nuropb-inspired and will need their own vocabulary — to be defined during
architecture scoping.

## Correctness: spec consistency (SMT) + Lean proofs

Correctness for the key patterns rests on two layers of formal assurance,
applied in order:

1. **Specification consistency, checked by SMT solver (Z3 or CVC5), via the
   SpeC++ workflow.** Before any pattern's invariants are handed off for
   Lean proof work, they are formalized as SpeC++ clauses over an explicit
   sort universe and run through SpeC++'s mandatory `CheckSat` gate. A
   specification that is internally contradictory (UNSAT) or unresolvable by
   the solver (UNKNOWN) must be repaired and re-checked before proceeding —
   there is no point proving an implementation correct against a spec that
   can't itself be satisfied.
2. **Implementation correctness, proved in Lean.** For the key patterns, the
   project requires formal, machine-checked proofs that the Python
   implementation satisfies the (SMT-consistency-checked) specification —
   not just automated tests.

**Recommended sequencing for the Lean proof work** (open for revision as the
project develops):

1. **Phase 1 — Protocol/message-format correctness.** Prove properties of the
   connection/channel/consumer lifecycle as a state machine, and of message
   correlation (e.g., every RPC reply correlates to exactly one outstanding
   request). This is the more tractable formalization target and directly
   protects the highest-risk part of writing a native AMQP implementation.
2. **Phase 2 — Concurrency/ordering & delivery guarantees.** Prove
   higher-level properties such as "a request always eventually yields
   exactly one reply or a well-defined timeout/error," ordering guarantees,
   and duplicate-delivery avoidance under reconnect. This requires modeling
   the network and RabbitMQ's own guarantees (likely as axioms) and is a
   larger formalization effort, to be tackled once Phase 1 establishes a
   template.

**Decided (v1 coupling):** SpeC++ consistency-checks the specification
first; Lean models Protocol/Session invariants second; the Python
implementation is kept aligned via **property-based tests derived from the
Lean model plus manual correspondence review**. Code extraction /
generated implementation is explicitly out of scope for v1 — see
`architecture.md`, "Lean-to-Python coupling."

## Project goals

Beyond functional pattern parity, this project is explicitly optimizing for:

- **Trust.** Correctness of the key patterns should be demonstrable, not just
  asserted — this is the primary motivation for the spec-consistency (SMT)
  and Lean proof requirements above, and it should also inform choices like
  the mTLS support, explicit (non-silent) TLS hostname verification, and
  spec-pure JSON-RPC bodies: behavior should be verifiable and predictable
  rather than "probably fine."
- **Robustness.** The library should behave correctly and predictably under
  failure — broker disconnects, reconnects, partial network failures, broker
  restarts/failover — not just on the happy path. This is a large part of why
  Phase 2 of the Lean work (ordering/delivery guarantees under reconnect) is
  in scope rather than a nice-to-have.
- **Highest achievable throughput.** Removing nuropb's current layers of
  abstraction and third-party dependency (`pika` and everything wrapped
  around it) is partly about a leaner dependency footprint, but is also
  explicitly a performance goal: a native, purpose-built AMQP implementation
  should be able to minimize overhead (allocation, copying, serialization,
  event-loop scheduling) in the hot path in ways a general-purpose
  abstraction layer cannot. Throughput should be treated as a first-class,
  measured property of the implementation, not an incidental side effect of
  cutting dependencies.

These three goals will need to be weighed against each other in specific
design decisions (e.g., Lean-provable simplicity vs. throughput-optimized
complexity in the hot path) — trade-offs should be made explicitly and
recorded, not resolved silently in code.

## Trust boundary

nuropb-rmq's Lean/SpeC++ proofs cover the correctness of its own
client-side protocol/session/pattern logic given that AMQP-level
permissions (who may publish to a reply queue, who may bind to a service
namespace) are correctly configured by the deployment. Those permissions
are a RabbitMQ/vhost configuration concern and a deployment prerequisite,
not something the Lean proofs themselves establish. This is stated
alongside what nuropb-rmq inherits, rather than proves — message
durability, replication, crash recovery, and routing-table consistency
under cluster partition all come from RabbitMQ's own track record, not
from this project's formal methods — so the scope of the trust claim isn't
misread as covering broker authorization as well as broker durability and
replication.

**Also out of Lean scope:** claims/token *issuance* and *revocation* (IdP).
The library verifies and propagates JWTs (`exp`, `jti`↔correlation id,
`method` binding) but does not mint or revoke them. Required broker
permission profiles (`reply-publish-restricted`, `mesh-bind-namespaced`)
are documented in `architecture.md`.

## Core architectural invariant: no conflation, no multi-path outcomes

This is a governing principle for the project, not a preference: **terms,
meanings, and behaviors must not be conflated, and for a given set of
inputs there must be exactly one defined path and one defined outcome — not
several mechanisms that can independently produce different results for the
same situation.**

This is stated explicitly because it is easy to violate quietly, one
reasonable-looking decision at a time — two independent timeout mechanisms,
two ways of naming the same field, two subsystems each with their own
opinion about what a given message means. Each individual addition can look
harmless; the accumulated effect is a system where the same input can lead
to different outcomes depending on incidental timing, and where nobody can
say with confidence what "correct behavior" is because there are several
competing definitions of it. That is fundamentally incompatible with the
project's trust and robustness goals above — a system can't be trusted or
proven robust if its own behavior isn't singular and well-defined to begin
with.

Concretely, this invariant means:

- **One authoritative mechanism per concern**, not several mechanisms racing
  or overlapping to produce the "same" result. Where a secondary mechanism
  exists (e.g. a fallback), its scope of applicability must be
  **mutually exclusive** with the primary mechanism's — not a parallel path
  that can independently fire for the same input.
- **One name, one meaning, per concept**, even when a value is carried in
  more than one place for interoperability reasons (e.g. a correlation id
  exposed as both an AMQP property and a JSON-RPC field) — the two
  accessors must be provably, structurally kept identical, never
  independently settable, so they can never diverge into "the AMQP layer's
  version" versus "the JSON-RPC layer's version" of what should be one
  fact.
- **Decisions already made in this project are direct instances of this
  invariant**, worth naming explicitly as precedent:
  - The correlation id / JSON-RPC id are a single value with two accessors,
    never independently generated (see architecture.md, "Reply routing" and
    "Session layer").
  - Broker-side TTL/DLQ was made the *sole* authoritative timeout mechanism
    (with RabbitMQ present) specifically *because* the alternative — a
    client-side timer running in parallel — could produce two different,
    conflicting outcomes (client-declared failure vs. genuine service
    success) for the same request. The client-side fallback is scoped to be
    mutually exclusive with the broker-side path (engaged only when the
    broker doesn't provide the capability), not a second opinion running
    alongside it.
  - Nuropb-specific application error codes were deliberately placed outside
    JSON-RPC's shared "server error" range specifically to avoid two
    different systems silently attaching two different meanings to the same
    code.
- **This invariant should be checked, not just aspired to.** It belongs in
  the SMT-consistency-checked specification layer alongside the other
  invariants already scoped there (id consistency, error-code namespace
  separation, durable/persistent pairing): a specification admitting two
  different reachable outcomes for the same input state should fail
  consistency checking, the same way a self-contradictory spec does.
- **Every future architectural decision in this project should be checked
  against this invariant before being finalized**: does this introduce a
  second path, a second name, or a second meaning for something that
  already has one? If so, either eliminate the duplication, or make the
  relationship between the two explicit, structural, and mutually
  exclusive — never left as an implicit "usually these agree."

## Open / resolved planning items

Status of the questions that previously sat as an untitled list at the end
of this document. Detail lives in `architecture.md` (Decision ledger).

| Item | Status |
|---|---|
| Concrete architecture (transport, protocol SM, session, patterns, Lean) | **Resolved** — see `architecture.md` layering and package layout |
| Which pattern to implement and formally spec first | **Resolved** — Transport+Protocol first; RPC/Session next; mesh/claims later (sequencing in `architecture.md`) |
| How far JSON-RPC 2.0 extends into mesh/claims | **Resolved** — JSON-RPC body stays spec-pure; mesh/claims travel in AMQP headers only |
| How Lean specs couple to the Python implementation | **Decided** — SpeC++ consistency → Lean model → property-based tests derived from the model + manual correspondence review; no code extraction in v1 (see `architecture.md`) |
