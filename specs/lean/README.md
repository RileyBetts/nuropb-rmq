# NuropbRmq Lean specs (Protocol + Session + Pattern)

Lean 4.33 model and proofs of:

- Protocol connection/channel invariants 1–7, `update-secret`, blocked publish,
  heartbeat miss-count
- Publisher confirms, delivery settle, `basic.return` then confirm-ack
- Session correlation (Phase 1b) and park/fail-fast reconnect (Phase 2)
- Pattern mesh bind, fail-closed claims, **executable HS256 JWT**, ACL profiles
- SHA-256 / HMAC (computable; not hardness proofs)

```bash
cd specs/lean
lake build
```

See [CORRESPONDENCE.md](CORRESPONDENCE.md) for Lean ↔ Python mapping.
See `../specpp/` for the SpeC++ SMT CheckSat gate that precedes these proofs.
