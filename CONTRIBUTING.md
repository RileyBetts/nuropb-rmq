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
Both are protected: changes land via pull request with required CI.

```text
feature/<name>  →  development  →  main
```

1. Update and branch from `development`:

```bash
git checkout development && git pull
git checkout -b feature/my-change
```

2. Open a PR targeting **`development`** (squash merge preferred).
3. When `development` is ready to release, open a PR **`development` → `main`**
   (merge commit preferred so the integration boundary is visible).

Do not push directly to `main` or `development`.

## CI / gates

GitHub Actions (`.github/workflows/ci.yml`) runs these gates via uv. Locally:

```bash
uv sync --dev
uv lock --check
uv run ruff check src tests
uv run python specs/specpp/check_sat.py
uv run pytest -q -m "not integration and not benchmark and not fuzz" --cov=nuropb_rmq --cov-fail-under=50
HYPOTHESIS_PROFILE=ci uv run pytest -q -m fuzz
uv sync --dev --extra claims && uv run pytest -q tests/patterns/test_context.py
# with RabbitMQ on 5672 (or set NUROPB_RMQ_HOST / NUROPB_RMQ_PORT):
uv run pytest -q -m integration
(cd specs/lean && lake build)
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
```

AMQPS / mTLS opt-in tests: see README TLS section and
`tests/integration/test_amqps_*.py` plus scripts under `scripts/`.

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

## Alpha → beta

Stay on **Alpha** (`Development Status :: 3 - Alpha`) until all of the following
are true. Park-and-retry across reconnect stays deferred (fail-fast is v1).

- `basic.return` / mandatory publish shipped and tested (done in 0.5.0)
- At least one external operator has run AMQPS + restricted reply-publish
  (`scripts/reply-publish-restricted.md`)
- Public API freeze note: no silent additions/renames in `nuropb_rmq.api`
  without a changelog entry
- Unit coverage measured in CI (`pytest-cov`, `--cov-fail-under=50` on the unit
  lane — a regression floor, not a vanity target; live transport/RPC is
  exercised in the integration job)
- No new claims beyond protocol/session proof scope (SpeC++ / Lean)

TTL anti-enumeration *timing* tests and management-API permission audits are
soft follow-ups, not beta blockers.

