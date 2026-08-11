# Contributing

## Setup

```bash
uv sync --dev
```

Use `uv run …` for pytest, ruff, and example scripts. Add product extras as needed
(e.g. `uv sync --dev --extra claims`). There is no `[dev]` package extra — maintainer
tooling is the PEP 735 `dev` dependency group.

## Branching

Use the **feature → development → main** flow documented in [`README.md`](README.md#branching).

- Branch from `development`, open PRs into `development`.
- Release by opening a PR from `development` into `main`.
- Do not push directly to `main` or `development`; both require a PR and green CI.

Prefer squash merge for feature PRs and a merge commit for `development` → `main`.
