# SpeC++ specs (Protocol + Session)

SMT-LIB encodings of Protocol connection/channel invariants 1–7 and Session
Phase 1b correlation invariants from `thinking/architecture.md`.

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

**UNKNOWN is a hard failure** (no waiver).
