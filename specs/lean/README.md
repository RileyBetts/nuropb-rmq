# NuropbRmq Lean specs (Protocol Phase 1 + Session Phase 1b)

Lean 4.33 model and proofs of Protocol connection/channel invariants 1–7 and
Session correlation invariants (id format, dual-accessor, collision reject,
first-reply-wins, reply-queue lifetime brackets table).

```bash
cd specs/lean
lake build
```

See [CORRESPONDENCE.md](CORRESPONDENCE.md) for Lean ↔ Python mapping.
See `../specpp/` for the SpeC++ SMT CheckSat gate that precedes these proofs.
