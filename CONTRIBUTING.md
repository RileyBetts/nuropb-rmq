# Contributing

## Setup

Requires [uv](https://docs.astral.sh/uv/). Python is pinned in `.python-version` (3.12).

```bash
uv sync --dev
```

Use `uv run …` for pytest, ruff, and example scripts. Add product extras as needed
(e.g. `uv sync --dev --extra claims`). There is no `[dev]` package extra — maintainer
tooling is the PEP 735 `dev` dependency group. Committed `uv.lock` is the supported
lockfile (CI runs `uv lock --check`).

## Branching

Long-lived branches: **`development`** (integration) and **`main`** (stable/release).
**Both are protected.** GitHub must require pull requests and passing CI. There
is no direct push, no force-push, and no commit on those branches from a
workstation or an agent.

Every change — including docs, CI, and version bumps — is introduced on a
**feature branch**:

```text
feature/<name>  →  development  →  main
```

1. Update and branch from `development` (never from `main` for feature work):

```bash
git checkout development && git pull
git checkout -b feature/my-change
```

2. Open a PR targeting **`development`** (squash merge preferred).
3. When `development` is ready to release, open a PR **`development` → `main`**
   (merge commit preferred so the integration boundary is visible).
4. Annotated `v*` tags are cut from **`main`** only, after that PR has landed.

Do not push directly to `main` or `development`. Do not open feature PRs into
`main`. Do not merge `main` into a feature branch as a substitute for
branching off `development`.

## CI / gates

GitHub Actions (`.github/workflows/ci.yml`) runs these gates via uv. Attack
surfaces, SpeC++ negatives, and the exhaustive local command list:
[`docs/reference/testing-regime.md`](docs/reference/testing-regime.md).

Locally:

```bash
uv sync --dev
uv lock --check
uv run ruff check src tests
uv run python specs/specpp/check_sat.py
uv run pytest -q -m "not integration and not benchmark and not fuzz" --cov=nuropb_rmq --cov-fail-under=50
HYPOTHESIS_PROFILE=ci uv run pytest -q -m fuzz
uv sync --dev --extra claims && uv run pytest -q tests/patterns/test_context.py tests/patterns/test_jwt_golden.py
# with RabbitMQ on 5672 (or set NUROPB_RMQ_HOST / NUROPB_RMQ_PORT):
uv run pytest -q -m integration
# from repository root (nested specs/lean is not the Lake package)
lake build NuropbRMQSpec   # proofs, no sockets
lake build NuropbRMQ       # POSIX client
lake exe oracle .          # golden vectors (specs/vectors/)
```

Claims + mesh integration:

```bash
uv sync --dev --extra claims
uv run pytest -q tests/patterns/test_context.py tests/integration/test_mesh_claims_amqp.py
```

Example smoke (needs a broker). LangChain / LangGraph suites also need
`uv sync` inside `examples/langchain_example` and `examples/langgraph_example`
first:

```bash
./scripts/smoke_examples.sh
# Lean ↔ Python interop (needs lake + broker):
./scripts/smoke_interop.sh
```

AMQPS / mTLS tests: see README TLS section,
`tests/integration/test_amqps_*.py`, `./scripts/smoke_lean_amqps.sh`, and
`./scripts/smoke_lean_mtls.sh`. `lean-mtls` is not required to merge.

## Publishing

Pushing an annotated tag `vX.Y.Z` from `main` runs
[`.github/workflows/publish.yml`](.github/workflows/publish.yml), which builds
the sdist/wheel and uploads to PyPI via Trusted Publishing (OIDC). The tag
must match `[project].version` in `pyproject.toml`.

### One-time Trusted Publisher setup

1. On PyPI, add a Trusted Publisher (or **pending** publisher for the first
   upload) for project `nuropb-rmq`:
   - Owner: `RileyBetts`
   - Repository: `nuropb-rmq`
   - Workflow: `publish.yml`
   - Environment: `pypi`
2. In this GitHub repo: Settings → Environments → create `pypi` (optional
   protection rules are up to maintainers).
3. Confirm the package name is available / owned on PyPI before the first tag.

## 1.0 release criteria

Stay off **Production/Stable** until all of the following are true (this tree
targets 1.0.0):

- Park-and-retry default reconnect, with fail-fast as `fail_outstanding=True`
- Lean HS256 JWT verify + broker ACL profiles (`reply-publish-restricted`,
  `mesh-bind-namespaced`) with SpeC++ / correspondence tests
- AMQPS `tls-verify-full` and reply-publish ACL exercised in CI
- Public API freeze: [`docs/reference/api-stability.md`](docs/reference/api-stability.md)
- Unit coverage measured in CI (`pytest-cov`, `--cov-fail-under=50` on the unit
  lane — a regression floor, not a vanity target)
- `specs/lean/CORRESPONDENCE.md` re-audited for the tag

mTLS / SASL `EXTERNAL` (PEM or PKCS#12) is Lean + Python (`lean-mtls`, not
required to merge). RS256/ES256 verify is `NuropbRMQTls` (OpenSSL). HMAC
hardness stays residual.

Celery parity, LangGraph-in-core, `basic.get` / Tx / purge stay out of tree.

