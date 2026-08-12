# Architecture overview

A short visual tour for integrators. Deep design decisions live in
[`thinking/architecture.md`](../../thinking/architecture.md) — this page stays
at the “what talks to what” level.

## Layer stack

```mermaid
flowchart TB
  app[Application]
  pattern[Pattern_RPC_mesh_events_claims]
  session[Session_correlation_reply]
  protocol[Protocol_AMQP_state_machines]
  transport[Transport_TCP_TLS_frames]
  proofs[Lean_and_SpeCpp_proofs]

  app --> pattern
  pattern --> session
  session --> protocol
  protocol --> transport
  proofs -.-> session
  proofs -.-> protocol
```

Your code uses **Pattern** APIs (`RpcClient`, `MeshService`, events) or drops
down to **Transport** (`AmqpConnection`). **Session** owns exclusive reply
queues and correlation ids. **Lean / SpeC++** are parallel proof artifacts —
they are not a runtime dependency.

## Mesh RPC path

```mermaid
sequenceDiagram
  participant Client as RpcClient
  participant ReplyQ as nr_reply_exclusive
  participant Broker as RabbitMQ
  participant SvcQ as service_method_queue
  participant Server as RpcServer

  Client->>Broker: publish request to service.method
  Note over Client,ReplyQ: Session declares exclusive reply queue
  Broker->>SvcQ: route by binding
  SvcQ->>Server: deliver request
  Server->>Broker: publish reply to nr.reply.*
  Broker->>ReplyQ: deliver reply
  ReplyQ->>Client: resolve correlation id
```

Clients wait on a per-connection exclusive reply queue. Services bind only
under their `service.method` namespace. Broker ACLs must allow services to
publish replies — see [Broker permissions](../guides/broker-permissions.md).

## AMQPS connect

```mermaid
flowchart LR
  cfg[ConnectionConfig]
  mat[Resolve_TlsMaterial]
  ssl[SSL_profile_verify]
  tcp[TCP_plus_TLS]
  sasl[SASL_PLAIN_or_EXTERNAL]

  cfg --> mat
  mat --> ssl
  ssl --> tcp
  tcp --> sasl
```

Material can come from files, in-memory PEM, PKCS#12, or a `tls_secrets` hook
(re-run on every `connect()`). Profile **`tls-verify-full`** checks chain and
hostname. `EXTERNAL` is used only when the broker advertises it **and** a
client cert is configured — never assume mTLS alone means passwordless.
Details: [TLS profiles and material](tls-profiles-and-material.md) and
[Cloud AMQPS](../guides/cloud-and-enterprise-amqps.md).

## Claims on the wire

```mermaid
flowchart TB
  body[JSON_RPC_body]
  headers[AMQP_headers]
  jwt[nr_claims_JWT]
  typ[nr_claims_typ_JWT]

  body --- headers
  headers --> jwt
  headers --> typ
```

Application auth rides in AMQP **headers** only; the JSON-RPC body stays
spec-pure. Servers with `AuthConfig` fail closed on missing or unbound tokens.
See [JWT claims](jwt-claims.md).

## Reconnect (v1)

```mermaid
flowchart LR
  lost[Disconnect]
  fail[Outstanding_RPCs_CONNECTION_LOST]
  epoch[New_connection_epoch]
  rebind[Caller_reconnect_and_rebind]

  lost --> fail
  fail --> epoch
  epoch --> rebind
```

There is no silent park-and-retry of in-flight RPCs. After reconnect you must
rebind mesh consumers and restart servers. See [Reconnect](reconnect.md).

Publisher confirms and `connection.blocked` fail-fast (no silent stall) are part
of the same robustness story — see queue profiles and connection config docs.

## Next

- [Service mesh](service-mesh.md) — what “mesh” means here
- [Connection config](connection-config.md)
- Runnable mesh demo: [`examples/one_client_one_service/`](../../examples/one_client_one_service/)
