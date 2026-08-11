# Reply-queue publish restriction (deployment prerequisite)

Permission profile name: **`reply-publish-restricted`**

## Why

Clients declare exclusive reply queues named `nr.reply.<connection_id>`.
Any publisher that can write to those queues can forge RPC replies. The
broker ACL is the hard gate; the library documents the required shape and
does not replace RabbitMQ permissions.

## Required shape

| Actor | Configure |
|-------|-----------|
| Mesh / RPC service users | May **publish** to `nr.reply.*` (or your configured reply-queue prefix) when completing requests |
| Ordinary clients | May **declare/consume** their own `nr.reply.*` exclusive queues; should **not** publish to other clients' reply queues |
| Default guest / wildcard | Avoid `configure=.*` / `write=.*` on `/` for untrusted users |

### rabbitmqctl sketch

```bash
# Service identity: can publish replies + work the mesh namespace
rabbitmqctl set_permissions -p / svc-orders \
  "^nr\.svc\.orders$|^nr\.reply\." \
  "^nr\.mesh.*|^nr\.reply\..*|^nr\.dlx\..*" \
  "^nr\.svc\.orders$|^nr\.mesh.*|^nr\.dlx\..*"

# Client identity: exclusive reply queue only (adjust regex to your vhost policy)
rabbitmqctl set_permissions -p / client-app \
  "^nr\.reply\." \
  "^nr\.mesh.*|^nr\.reply\." \
  "^nr\.reply\."
```

Exact regexes depend on your exchange/queue naming. Prefer topic permissions
(`set_topic_permissions`) when using topic exchanges for mesh traffic.

## Ops checklist

- [ ] No shared user with `write=.*` that can reach another process's `nr.reply.*`
- [ ] Service users allowed to publish to the reply-queue prefix used by Sessions
- [ ] Clients can declare exclusive `nr.reply.*` queues for their connection
- [ ] Documented alongside `mesh-bind-namespaced` in runbooks
- [ ] Optional: management-API audit that permissions match this shape (not required by the library)

## Related

- Mesh bind profile: `mesh-bind-namespaced` (client-side namespace guard in `MeshService`)
- Optional discovery: fanout `nr.mesh.registry` (`MeshService(announce=True)` /
  `MeshRegistryViewer`) — never replaces broker bind permissions
- Session reply queues: `Session.start` → `nr.reply.{connection_id}`
