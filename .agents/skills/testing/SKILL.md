---
name: testing
description: Where tests live, how to run them, and what to test in the Renly repo. Use when writing or running tests.
---

# Testing (Renly)

## Current state

- **API tests:** `apps/api/tests/unit/` — pytest, ~850 tests across ~50 files covering metrics/date/liquidity helpers, service flows (mocked sessions/repos), schema validation, and in-process endpoint behavior.
- **Web E2E tests:** `apps/web/tests/e2e/` — Playwright. See the `e2e-testing` skill for full conventions, configuration, and the playwright-cli workflow.
- **Web component/unit tests:** None planned. E2E is the only web test layer for now.
- **Pre-commit:** `pnpm test:api` runs on every commit. Also runs in CI (`ci.api.yml`).

## Running tests

```bash
# From apps/api
uv run pytest tests/ -v

# From repo root
pnpm test:api

# From apps/web
pnpm test:e2e
```

## Boundary between layers

- **API logic** (formulas, transformations, repository/service behavior) → pytest in `apps/api/tests/`.
- **User-facing flows** (login, transactions, dashboard render, navigation) → Playwright E2E in `apps/web/tests/e2e/`. See `e2e-testing` for specifics.

## What to test (API)

**Unit test** (`tests/unit/` — no real database):

- Pure calculation/transformation functions in `services/` or `utils/` (formulas, parsers, date math).
- Service flows with mocked sessions/repositories (`unittest.mock.AsyncMock`, `monkeypatch`).
- Endpoint behavior driven **in-process** (FastAPI TestClient / ASGI transport with overridden
  dependencies — auth, session). These still count as unit tests: no network, no Postgres.

**Integration test** (`tests/integration/` — a live database):

- Tests that need a real Postgres (schema, roles, RLS). Today: `test_rls_isolation.py`, gated on
  `RLS_TEST_DATABASE_URL` + `RLS_TEST_ADMIN_DATABASE_URL` and skipped when unset, so the default
  `pnpm test:api` run stays green without a DB.

**Don't test:**

- Framework behaviour (FastAPI routing, SQLModel field types)
- Simple CRUD with no logic (list, get by id, delete)

## File structure

```
apps/api/tests/
├── unit/           # no real DB: pure functions, mocked-session services, in-process TestClient
└── integration/    # live-DB only (env-gated; skipped by default)
```

There is no shared `conftest.py` — tests build their own fixtures/mocks per file.

## Fixtures

- Use `pytest-asyncio` for async services/routes.

## Assertions

- Test the formula result with known inputs and manually computed expected values — don't test by calling the formula twice
- For currency conversion: use hardcoded exchange rates in fixtures, not live API calls
