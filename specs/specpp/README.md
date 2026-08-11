# SpeC++ specs (Protocol + Session + Pattern)

SMT-LIB encodings of Protocol invariants 1–7, Session Phase 1b correlation,
and Pattern mesh/claims fail-closed clauses from `thinking/architecture.md`.

## CheckSat gate

```bash
python specs/specpp/check_sat.py
```

| File | Expected |
|---|---|
| `Protocol/connection_channel_sm.smt2` | **sat** |
| `Protocol/connection_channel_sm_negatives.smt2` | **unsat** |
| `Session/correlation.smt2` | **sat** |
| `Session/correlation_negatives.smt2` | **unsat** |
| `Pattern/mesh_claims.smt2` | **sat** |
| `Pattern/mesh_claims_negatives.smt2` | **unsat** |

**UNKNOWN is a hard failure** (no waiver).
