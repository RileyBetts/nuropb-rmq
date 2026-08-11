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
uv run pytest -q -m "not integration and not benchmark and not fuzz"
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

Example smoke (needs a broker):

```bash
./scripts/smoke_examples.sh
```

AMQPS / mTLS opt-in tests: see README TLS section and
`tests/integration/test_amqps_*.py` plus scripts under `scripts/`.
