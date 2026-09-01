# SpeC++ specs (Protocol + Session + Pattern + Phase 2)

SMT-LIB encodings of Protocol invariants 1–7, Session correlation, Pattern
mesh/claims, and Phase 2 reconnect/TTL terminal-state clauses from
`thinking/architecture.md`.

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
| `Session/phase2_reconnect.smt2` | **sat** |
| `Session/phase2_reconnect_negatives.smt2` | **unsat** |
| `Pattern/mesh_claims.smt2` | **sat** |
| `Pattern/mesh_claims_negatives.smt2` | **unsat** |
| `Config/queue_profile.smt2` | **sat** |
| `Config/queue_profile_negatives.smt2` | **unsat** |
| `Protocol/publisher_confirms.smt2` | **sat** |
| `Protocol/publisher_confirms_negatives.smt2` | **unsat** |
| `Protocol/connection_blocked.smt2` | **sat** |
| `Protocol/connection_blocked_negatives.smt2` | **unsat** |
| `Protocol/basic_return.smt2` | **sat** |
| `Protocol/basic_return_negatives.smt2` | **unsat** |
| `Protocol/update_secret.smt2` | **sat** |
| `Protocol/update_secret_negatives.smt2` | **unsat** |
| `Protocol/heartbeat_watchdog.smt2` | **sat** |
| `Protocol/heartbeat_watchdog_negatives.smt2` | **unsat** |
| `Session/park_reconnect.smt2` | **sat** |
| `Session/park_reconnect_negatives.smt2` | **unsat** |
| `Pattern/acl.smt2` | **sat** |
| `Pattern/acl_negatives.smt2` | **unsat** |

**UNKNOWN is a hard failure** (no waiver).
