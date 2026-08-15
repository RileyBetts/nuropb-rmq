# nuropb-rmq v0.2.0 vs pika — AMQP 0-9-1 completeness reassessment

Re-assessment after v0.2.0 (commit `ad89380`, PR #19 "Close AMQP P0/P1 gaps:
confirms, blocked, body frames, nack/cancel"), following the earlier v0.1.0
review. Claims below are verified against source (file:line) and, where noted,
by running the actual encoder/decoder.

**v0.5.0 follow-up:** `basic.return` / mandatory publish, the five missing
content properties, and `connection.update-secret` are implemented. Remaining
delta vs pika is the documented non-goals (`basic.get`, Tx, Access,
`channel.flow`, delete/unbind/purge).

## What v0.2.0 closed (verified against source, not just the changelog)

| Gap flagged last time | Status now |
|---|---|
| No publisher confirms | ✅ `confirm.select` + `ConfirmTracker` (`src/nuropb_rmq/transport/confirm.py`) — `basic_publish` auto-enables confirms for durable profiles and awaits ack/nack; `multiple`-ack semantics handled correctly, outstanding futures fail on connection loss |
| No `basic.nack`/`reject`, DLX had no on-demand trigger | ✅ Both wired (`connection.py:618-673`); `NackDelivery` exposed on the RPC path (`patterns/rpc.py`) for poison-message → DLX |
| `connection.blocked`/`unblocked` silently dropped | ✅ Handled; sets `_publish_blocked`, refuses further publishes with `ConnectionBlockedError`, optional user callbacks (`connection.py:816-840`) |
| `basic.cancel` defined but dead | ✅ Full round-trip (`basic_cancel` → `CANCEL_OK`) |
| Outbound body fragmentation absent; off-by-8 at `frame_max` boundary | ✅ Fixed both: `basic_publish` now chunks across multiple BODY frames (`connection.py:553-561`), and `max_frame_payload()` correctly reserves the 8-byte frame overhead so a payload of exactly `frame_max - 8` is the true ceiling — verified this matches the AMQP spec's "total frame size ≤ frame_max" definition |
| Field-table encoder missing float/list/Decimal/datetime | ✅ All four added (`frame.py:149-188`) |
| `connection.secure` would hang 10s then fail opaquely | ✅ Now rejected immediately and explicitly on receipt, rather than timing out |

Verification performed directly (not just read): `encode_table({"x": 1.5})` and
`encode_table({"x": ["a"]})` — both previously raised `AmqpCodecError`, both now
encode successfully.

## What's still absent — and it's now a documented boundary, not an accidental gap

`docs/concepts/queue-profiles.md:41-42` states the non-goals outright: `basic.get`,
`Tx`, `Access`, `channel.flow`, exchange/queue delete/unbind/purge. Verified
against `methods.py` — all still genuinely absent, matching the doc exactly.
Also still missing but *not* mentioned in that non-goals list:

- **`basic.return`** — `basic_publish` still hardcodes `mandatory: False`
  (`connection.py:545`), so mandatory-publish/unroutable-message handling
  remains unreachable. Minor since confirms now cover the "did the broker take
  it" question that `mandatory` is usually reached for.
- **`connection.update-secret`** — still absent; still the one gap that's
  slightly in tension with the project shipping a JWT-claims extra and a
  TLS-rotation secrets hook, since that's the credential-refresh path AMQP
  defines for exactly this scenario.
- **5 of 14 `basic` content properties** (`timestamp`, `type`, `user_id`,
  `app_id`, `cluster_id`) — unchanged from before; a nuropb consumer still
  silently drops these fields from a pika-published message.
- **Exchange-to-exchange bind/unbind, `Tx` class** — both fine to skip
  (RabbitMQ-modern and rarely-used-in-general respectively); pika supports
  them since it's general-purpose.

## Net assessment

v0.2.0 closed every gap that mattered for the project's own stated guarantees —
the "durable-at-least-once" doc claim is now actually backed by confirms
end-to-end, and there's a real poison-message path via nack→DLX. The remaining
delta versus pika is now a **declared, intentional subset** (continuous-consume
+ declare-your-own-topology, no admin/management methods) rather than silent
gaps discovered by reading code. The two things still worth flagging: `update-
secret` given the JWT/TLS-rotation surface already in the project, and the 5
missing content properties, since neither is in the documented non-goals list
and both are cheap to add if they ever bite someone interop-testing against
pika-published messages.
