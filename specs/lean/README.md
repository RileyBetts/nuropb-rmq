# NuropbRmq Lean specs (Protocol + Session Phase 1b + Phase 2)

Lean 4.33 model and proofs of:

- Protocol connection/channel invariants 1–7
- Session correlation (Phase 1b)
- Dead-letter/TTL exclusivity + reconnect epochs (Phase 2)

```bash
cd specs/lean
lake build
```

See [CORRESPONDENCE.md](CORRESPONDENCE.md) for Lean ↔ Python mapping.
See `../specpp/` for the SpeC++ SMT CheckSat gate that precedes these proofs.
