# SpeC++ Protocol SM

SMT-LIB encodings of the Protocol connection/channel state-machine
invariants from `thinking/architecture.md` (invariants 1–7).

## CheckSat gate

```bash
python specs/specpp/check_sat.py
# or: z3 -smt2 specs/specpp/Protocol/connection_channel_sm.smt2
```

- `connection_channel_sm.smt2` must be **sat** (spec admits a model).
- `connection_channel_sm_negatives.smt2` must be **unsat** (forced
  invariant violations are contradictory).
- **UNKNOWN is a hard failure** (no waiver).
