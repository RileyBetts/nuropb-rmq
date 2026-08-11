# Security Review: nuropb-rmq (Native AMQP Service Mesh)

**Status:** Living review against the implemented library. Core Transport /
Protocol / Session / Pattern paths exist under `src/nuropb_rmq/`; findings here
remain invariants, deployment prerequisites, and test/fuzz obligations. Revisit
when `architecture.md` gains new Decided items.

**Relationship to the other project docs:** `project-intent.md` states *why*
and the project's goals (trust/robustness/throughput); `architecture.md`
states *what's decided*. This document states *what could go wrong and what
must be checked* — where a finding represents a genuine design gap, it should
also appear in the Decision ledger in `architecture.md`.

Gaps from this review have largely been folded into `architecture.md`.
Remaining soft follow-ups: TTL anti-enumeration *timing* tests
(content/allowlist covered by `tests/patterns/test_anti_enumeration.py`), and
management-API permission audits (optional; broker ACL remains authoritative).

**Frame fuzz in CI — done.** Dedicated Hypothesis lane: `tests/transport/test_frame_fuzz.py`
(`pytest -m fuzz`, `HYPOTHESIS_PROFILE=ci` in `.github/workflows/ci.yml`).

---

## 1. Transport Layer (TCP/TLS/mTLS, frame codec)

**This is the highest-risk layer** — a hand-rolled AMQP 0-9-1 parser is a
classic memory-safety and DoS surface, and it's explicitly in scope ("no
`pika`, no third-party AMQP client abstractions").

- **Malformed-frame parsing.** Frame length fields, content-header body-size
  fields, and table/field-array nesting in AMQP are attacker-controlled if
  the peer (or a MITM before TLS is up) is hostile. Even though the broker
  is nominally trusted, "trusted broker" is not "trusted bytes" — a
  compromised or spoofed broker, or a broker-in-the-middle during a
  downgrade attack, must not be able to crash or corrupt the client via a
  crafted frame. Concretely require:
  - Bounds-checked length prefixes before allocation (reject frames
    claiming sizes larger than a configured max *before* allocating
    buffers — an unbounded `frame_size` field read from the wire is a
    trivial memory-exhaustion vector).
  - No recursive/unbounded table nesting in `field-table` decoding (AMQP
    field tables can nest tables-in-tables; an attacker can nest deeply to
    cause stack exhaustion in a naive recursive decoder).
  - The architecture doc already flags this layer as "amenable to
    fuzzing" — good, but the invariant should be stated explicitly as a
    Lean/SpeC++ obligation, not just a testing note: **"decode never
    allocates memory proportional to an unvalidated attacker-supplied
    length before validating that length against a configured ceiling."**
    This belongs in Phase 1 alongside the handshake state machine.

- **TLS/mTLS downgrade and hostname verification.** "Explicit, overridable
  hostname verification" is a reasonable goal, but "overridable" is exactly
  the kind of knob that becomes a footgun.
  - The override must require an explicit, loud, non-default configuration
    value (not a boolean flag that silently defaults to permissive) — same
    "named profile, not scattered kwargs" pattern already used for
    durability config. A `verify_hostname=False`-style single kwarg
    conflates "I want custom DNS/CN matching for cluster nodes" with "I
    want no verification at all" — precisely the "conflation" anti-pattern
    the project's own governing invariant warns against.
  - The Phase 1 Lean proof "no AMQP negotiation reachable except through a
    completed, verified TLS handshake" needs to explicitly cover the case
    where TLS is configured but hostname verification is overridden — a
    proof that only covers the fully-verified case gives false assurance
    about the override path, which is exactly where a real deployment
    mistake will occur.
  - **SASL downgrade.** The `EXTERNAL`-vs-`PLAIN` negotiation (client picks
    from what the broker advertises in `connection.start`) is a
    MITM-relevant decision point: a network attacker capable of
    manipulating the handshake could in principle suppress `EXTERNAL` from
    the advertised mechanism list to force fallback to `PLAIN`. Since
    negotiation happens after TLS per the architecture, this is mitigated
    as long as the advertisement is itself protected by the already-verified
    channel — but this should be a **named, checked invariant**
    ("mechanism negotiation is only trusted when received over an
    already-verified TLS channel; an unencrypted advertisement is never
    accepted for auth-consequential decisions"), not an implicit
    consequence of layering. **Adopted** in Protocol SpeC++ outline.
  - **Certificate/key material sourcing** — the doc correctly requires
    uniform validation across file/bytes/secrets-manager sources, but
    doesn't mention **key material zeroization or logging hygiene**.
    Private key bytes should never be logged, included in exception
    messages/tracebacks, or retained beyond TLS context setup. Python
    doesn't give strong zeroization guarantees, but "never appears in a
    repr/log/traceback" is enforceable and testable. **Adopted** in
    `architecture.md` cert sourcing / rotation.
  - **Rotation race.** **Decided:** re-invoke secrets hook on each new
    connection; mid-connection expiry → orderly reconnect with fresh
    material (no in-place TLS hot-swap).

## 2. Protocol Layer (AMQP state machine)

- **State-machine desync as an attack surface, not just a bug class.** The
  Phase 1 Lean goal ("no method sent in a state the broker would reject")
  is a security property as much as a correctness one: a client driven into
  an illegal state by a malicious/compromised broker response (unexpected
  frame ordering, replayed `tune-ok`, a frame for a closed channel) should
  **fail closed** (reject and tear down), never fail open into an ambiguous
  state. Recommend an explicit invariant: **"every transition rejected by
  the state machine results in connection/channel teardown, never a silent
  no-op that leaves internal state and broker-observed state divergent."**
- **Heartbeat handling as a DoS/wedge vector.** Too-aggressive heartbeat
  timeout → false-positive disconnects under load (especially given the
  throughput goal may create event-loop scheduling pressure that delays
  heartbeat processing). Too-lax timeout → a dead/hostile peer kept alive
  indefinitely. This interacts directly with the throughput goal and
  deserves its own configuration-profile treatment, same as durability.

## 3. Session Layer — correlation, ids, reconnect

This is the layer with the most subtle attack surface, because it's where
internal bookkeeping meets attacker-influenceable input (caller-supplied
ids, redelivered/duplicate messages, reconnect state).

- **Correlation id predictability / collision.** UUID4 hex as default,
  validated-not-coerced format — good. Two things worth making explicit:
  - **Cross-tenant/cross-client isolation on the reply queue holds *only*
    because reply queues are per-connection exclusive** (the Reply routing
    decision). This should be named as a security property, not just a
    throughput/provability trade-off: if a future optimization revisits
    `amq.rabbitmq.reply-to` for throughput, that revisit must re-derive
    this isolation property. Flag the dependency explicitly so a future
    "let's use the fast path" change doesn't silently reopen an isolation
    gap while chasing throughput.
  - **Caller-supplied ids are an injection surface into the correlation
    table.** If multiple logical callers can share one underlying
    connection/session (e.g. a service forwarding requests from many
    upstream users over one mesh connection), a caller could deliberately
    choose an id colliding with another concurrent request's id to
    intercept its reply — "first reply wins, later messages discarded"
    combined with attacker-chosen ids makes this a real integrity issue in
    that shared-connection scenario, not just a hygiene one.
    **Decided in `architecture.md`:** reject (not regenerate) on collision.
- **Duplicate-response / DLQ-timeout race — "first reply wins" as an
  authentication gap.** The rule (duplicate real replies and late
  DLQ-synthesized timeouts both discarded as "no longer pending") is sound
  for its stated purpose, but has a blind spot: **it accepts the first
  message claiming a given correlation id from any source, with no check
  that the message originated from a service instance actually bound to the
  relevant `service.method`.** If AMQP-level authorization on the reply
  queue is misconfigured, "first reply wins" becomes "first *attacker*
  reply wins," and the legitimate reply is silently discarded as a harmless
  duplicate. This needs to be named as a required permission profile (reply
  queue publish restricted to the broker-mediated request/response path),
  not left implicit — the current design's threat model for this rule only
  covers availability/consistency under legitimate failure, not a
  malicious publisher forging a reply.
- **Reconnect/rebind window (Phase 2, correctly deferred, flag now).**
  Client-side republish-on-reconnect-uncertainty is a second duplication
  source layered on top of the already-accepted service-side at-least-once
  redelivery. Per the project's own "no multi-path outcomes" invariant,
  Phase 2 should model both duplication sources under one unified
  "at-least-once, idempotency is the application's responsibility"
  statement rather than accidentally introducing a second, differently
  shaped duplication mechanism.

## 4. Pattern Layer (RPC, events, mesh, context/claims)

- **Context/claims propagation via AMQP headers — consequential; now
  specified in `architecture.md`.** Claims travel in
  `basic.properties.headers`, kept out of the JSON-RPC body:
  - **Binding / replay / fail-closed — decided:** signed JWT in `nr.claims`;
    verify signature; require `exp`; `jti` = correlation id; `method` matches
    JSON-RPC method; fail-closed on missing/malformed; constant-time compare.
  - **Header injection / type confusion.** Deserialization of claims into
    the field-table should remain strict (reject unexpected nested types,
    don't coerce) — same discipline as correlation-id validation.
- **Mesh registration/binding — spoofed service registration.**
  **Decided:** broker-native namespaced permissions
  (`mesh-bind-namespaced`) as the hard gate; library refuses binds outside
  configured service namespace; no app-level registration authority in v1.

## 5. Error handling / information disclosure

- **`error.data` discipline.** JSON-RPC's `error.data` is free-form —
  nuropb-rmq should define an explicit allowlist for what's permitted:
  stack traces, internal hostnames/queue names, or broker-internal details
  (e.g. `x-death` header contents surfaced verbatim from DLQ-timeout
  synthesis) must not leak into a response that could cross a trust
  boundary to a less-privileged caller. This is the kind of thing that gets
  added incidentally during implementation (someone dumps an exception's
  `str()` into `data` for debuggability) and should be a named, tested
  constraint now.

## 6. Probabilistic / non-deterministic attack considerations

- **UUID4 collision is not the relevant risk here.** Birthday-bound
  collision at 122 bits of entropy is not a practical attack surface at any
  realistic request volume. The actual probabilistic risk in this design is
  the **caller-supplied-id collision** issue above (§3), which is
  adversarial choice, not random collision — worth being precise about that
  distinction so effort isn't spent hardening UUID4 generation instead of
  validating caller input.
- **Timing side channels in id/claims validation.** If the "single
  validation function" for id format or claims verification does an
  early-return/short-circuit comparison (naive string equality on a token
  or HMAC), that's a textbook timing side channel. Requirement: **claims/
  token comparison uses constant-time comparison (`hmac.compare_digest` or
  equivalent), never `==`.**
- **TTL-based timeout as a probabilistic covert channel / enumeration
  oracle.** Because "dead-lettered due to TTL" and "successfully processed"
  are designed to be indistinguishable to the client, this is a good
  anti-enumeration property. **Decided as an explicit goal** in
  `architecture.md`: DLQ-synthesized timeout and “no such method” must not
  be distinguishable by timing/content alone across the public mesh API.
- **Redelivery-count-based poison-message DoS.** **Decided:** default
  profile `durable-at-least-once` uses quorum + `x-delivery-limit` + TTL
  (not TTL-only).

## 7. Trust-boundary framing (positive note, with two extensions)

The "Trust boundary" section in `project-intent.md` (nuropb-rmq proves its
own protocol/session correctness; does not claim to prove RabbitMQ's
broker-level guarantees) is genuinely good practice — it stops the Lean/
SpeC++ work from being overclaimed as covering partition tolerance or
storage durability. The following extensions are now **adopted** in
`architecture.md`:

1. **AMQP-level authorization** (who can bind/publish/consume on which
   exchange/queue) is a RabbitMQ/vhost configuration concern, not something
   nuropb-rmq's Lean proofs cover. Reply-queue and mesh-binding permission
   profiles are documented deployment prerequisites (`reply-publish-restricted`,
   `mesh-bind-namespaced`).
2. **Claims/token issuance and revocation are out of scope** (upstream IdP).
   nuropb-rmq verifies JWT signature/`exp`/`jti`/`method` binding and
   propagates claims; it does not mint or revoke tokens.

---

## Summary: invariants recommended for the SpeC++/Lean scope

| # | Invariant | Layer | Status |
|---|---|---|---|
| 1 | Frame decode never allocates proportional to unvalidated length before ceiling-check | Transport | Adopted — Protocol SM SpeC++ outline |
| 2 | AMQP negotiation unreachable without verified TLS, **including when hostname-verification override profile is set** | Transport | Adopted — TLS profiles in `architecture.md` |
| 3 | Mechanism negotiation only trusted over already-verified TLS channel | Protocol | Adopted |
| 4 | Every rejected state transition → teardown, never silent no-op | Protocol | Adopted |
| 5 | Caller-supplied correlation id rejected (not regenerated) on collision with any outstanding id in the same table | Session | **Decided** |
| 6 | Reply-queue delivery restricted to broker-authorized publishers (required AMQP permission profile `reply-publish-restricted`) | Session/Deployment | **Decided** |
| 7 | Method requiring claims validation has no code path treating missing/malformed claims as authorized | Pattern | **Decided** (fail-closed) |
| 8 | Claims payload bound (JWT sig + `exp` + `jti`=correlation id + `method`) to the specific request it authorizes | Pattern | **Decided** |
| 9 | Mesh binding requires namespace-scoped authorization; unauthorized bind to an existing `service.method` is rejected (broker ACL + client refuse-before-send) | Pattern | **Decided** (broker-native v1) |
| 10 | `error.data` content is allowlisted; internal details never surfaced verbatim | Pattern | **Decided** |
| 11 | Claims/token comparison is constant-time | Session/Pattern | **Decided** |

Items **5–9** were the must-resolve-before-implementation gaps; they are now
recorded as **Decided** in `architecture.md` (Decision ledger + Pattern/
Session sections). Revisit this table whenever `architecture.md` gains a
new Decided item.
