# Testing and proof regime

How `nuropb-rmq` is gated: **SpeC++ CheckSat → Lean 4 → property tests → live broker**.
UNKNOWN SMT is a hard failure. Lean does not extract Python. Correspondence is
manual: [`specs/lean/CORRESPONDENCE.md`](../../specs/lean/CORRESPONDENCE.md).

Commands below match [CONTRIBUTING](../../CONTRIBUTING.md) and
[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml). The CI job set is
the release floor; AMQPS mTLS is an extra local (and optional CI residual) lane.

## Layers

| Layer | What it proves | Gate |
|-------|----------------|------|
| SpeC++ sat | A legal world exists for the clause | `uv run python specs/specpp/check_sat.py` |
| SpeC++ **unsat** (negatives) | The named attack/contradiction is impossible in the model | same runner; UNKNOWN fails |
| Lean 4 proofs | Theorems over the same sorts (executable JWT/ACL/SHA-256, not hardness) | `lake build NuropbRMQSpec` (repo root) |
| Lean oracle | Golden frames / SM trace / ACL / JWT vs spec kernels | `lake exe oracle .` |
| Lean client | POSIX AMQP + mesh (`import NuropbRMQ`) | `lake build NuropbRMQ` |
| Unit + PBT | Python state machines, codec bounds, claims, ACL prefixes | `pytest -m "not integration and not benchmark and not fuzz"` |
| Frame fuzz | Malformed frames/tables never hang or ignore `frame_max` | `HYPOTHESIS_PROFILE=ci pytest -m fuzz` |
| Integration | Real RabbitMQ AMQP 0-9-1 behaviour | `pytest -m integration` |
| AMQPS | `tls-verify-full` PLAIN over TLS | `tests/integration/test_amqps_smoke.py` |
| mTLS | Client cert + SASL `EXTERNAL` (opt-in) | `tests/integration/test_amqps_mtls_smoke.py` |
| Example smoke | Vanilla, mesh, LangChain, LangGraph against a broker | `./scripts/smoke_examples.sh` |
| Lean↔Python interop | Shared `nr.interop.*` hello + mesh both directions | `./scripts/smoke_interop.sh` |
| Packaging | sdist/wheel metadata | `uv build && uvx twine check dist/*` |

Unit coverage is a **regression floor** (`--cov-fail-under=50` on the unit lane),
not a completeness claim. Live tests own most of `transport.connection` and RPC.

## Attack surfaces

Each row is a threat the suite is designed to catch. **unsat** means the SpeC++
negative encoding is contradictory; Lean/Python rows are decision procedures or
live broker checks, not cryptographic hardness.

| Surface | Attacker move | Model | Python / live |
|---------|---------------|-------|----------------|
| Codec / frames | Oversized or truncated frames, deep tables | `frame_bounds*_negatives.smt2` | `tests/transport/test_frame*.py`, fuzz lane |
| Handshake SM | Send methods out of order; AMQP during TLS handshake | `connection_channel_sm_negatives.smt2` | `tests/protocol/test_state_machines.py`, PBTs |
| `update-secret` | Rotate secret before `OPEN_OK` | `update_secret_negatives.smt2` | live `test_update_secret_same_password` |
| Flow control | Publish while `connection.blocked` | `connection_blocked_negatives.smt2` | `tests/transport/test_blocked_methods.py` |
| Heartbeat | Silent peer; miss-count | `heartbeat_watchdog_negatives.smt2` | `tests/transport/test_heartbeat.py` |
| Confirms vs return | Treat `basic.return` as nack; drop unroutable | `publisher_confirms_*`, `basic_return_*` | `tests/transport/test_{confirm,return}.py`, live return tests |
| Correlation | Colliding ids; second reply steals first; register with reply closed | `correlation_negatives.smt2` | `tests/session/test_correlation.py` |
| Reconnect | Fail-fast vs park mix-up; epoch not monotonic | `phase2_reconnect_*`, `park_reconnect_*` | session PBTs + live park/fail-fast/mesh rebind |
| Mesh bind | Bind outside `<service>.*` | `mesh_claims_negatives.smt2` | `test_mesh.py`; broker still required in prod |
| JWT / claims | Missing, bad sig, expired, `jti`≠corr, method mismatch | same Pattern negatives + Lean `tryAuth_*` | `test_context.py`, golden `test_jwt_golden.py`, live mesh claims |
| Reply forge | Client publish to another `nr.reply.*` via default exchange | `acl_negatives.smt2`; Lean `forgeDenied` | `test_acl.py`; live waits for `channel.close` **403** on `amq.default` |
| Error oracle | Distinct fields for timeout vs other mesh errors | (shape only; not SpeC++) | `test_anti_enumeration.py` |
| TLS | Skip verify; wrong hostname | outside Lean | AMQPS `VERIFY_FULL`; mTLS + `EXTERNAL` opt-in |
| Durability | Non-persistent publish on durable profile | `queue_profile_negatives.smt2` | `test_queue_profile.py` + live quorum RPC |

## What this regime does not claim

- HMAC/SHA-256 **hardness**; RS256/ES256; `authorize_func` in Lean
- RabbitMQ’s real regex ACL engine (Lean/Python prefixes; live test uses `amq.default` write)
- Exactly-once server execution under park-and-retry (at-least-once)
- Timing indistinguishability of errors
- Throughput (`-m benchmark` is optional, not CI)

## Local exhaustive run

Broker: Docker `rabbitmq:3-management` on `5672`/`15672` (wait until **healthy**,
not merely TCP accept). TLS: `scripts/gen_amqps_certs.sh` plus
`scripts/rabbitmq-amqps.ci.conf` on `5671`. mTLS: verify-peer conf, plugin
`rabbitmq_auth_mechanism_ssl`, user matching client cert CN.

```bash
uv lock --check
uv run ruff check src tests
uv run python specs/specpp/check_sat.py
lake build NuropbRMQSpec
lake build NuropbRMQ
lake exe oracle .
uv run pytest -q -m "not integration and not benchmark and not fuzz" \
  --cov=nuropb_rmq --cov-fail-under=50
HYPOTHESIS_PROFILE=ci uv run pytest -q -m fuzz
uv sync --dev --extra claims
uv run pytest -q tests/patterns/test_context.py tests/patterns/test_jwt_golden.py
# broker healthy:
uv run pytest -q -m integration
NUROPB_RMQ_TLS=1 NUROPB_RMQ_PORT=5671 NUROPB_RMQ_CA_FILE=dev/amqps/ca.pem \
  NUROPB_RMQ_SERVER_HOSTNAME=localhost \
  uv run pytest -q tests/integration/test_amqps_smoke.py
./scripts/smoke_examples.sh
./scripts/smoke_interop.sh
uv build && uvx twine check dist/*
```
