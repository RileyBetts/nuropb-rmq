# NuropbRmq Lean specs (Protocol + Session + Pattern)

Lean 4.33 model and proofs of:

- Protocol connection/channel invariants 1–7
- Publisher confirms, delivery settle, `basic.return` (distinct from nack)
- Session correlation (Phase 1b)
- Dead-letter/TTL exclusivity + reconnect epochs (Phase 2)
- Pattern mesh namespace bind + fail-closed claims (JWT crypto axiomatized)

```bash
cd specs/lean
lake build
```

See [CORRESPONDENCE.md](CORRESPONDENCE.md) for Lean ↔ Python mapping.
See `../specpp/` for the SpeC++ SMT CheckSat gate that precedes these proofs.
