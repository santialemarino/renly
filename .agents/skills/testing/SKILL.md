---
name: testing
description: Where tests live, how to run them, and what to test in the Renly repo. Use when writing or running tests.
---

# Testing (Renly)

## Current state

- **API tests:** `apps/api/tests/unit/` — pytest, ~850 tests across ~50 files covering metrics/date/liquidity helpers, service flows (mocked sessions/repos), schema validation, and in-process endpoint behavior.
- **Web unit tests:** `apps/web/tests/unit/` — Vitest (node environment), for pure functions — today the locale/formatting layer (`lib/i18n/`, `lib/utils/format|currency|numeric-input`) plus EN/ES translation keyset parity. Config: `apps/web/vitest.config.ts` (`vite-tsconfig-paths` wires the `@/*` alias). Run with `pnpm test:web`.
- **Web E2E tests:** `apps/web/tests/e2e/` — Playwright. See the `e2e-testing` skill for full conventions, configuration, and the playwright-cli workflow.
- **Pre-commit:** `pnpm test:api` + `pnpm test:web` run on every commit. Also run in CI (`ci.api.yml` / `ci.web.yml`).

## Running tests

```bash
# From apps/api
uv run pytest tests/ -v

# From repo root
pnpm test:api        # API unit tests (pytest)
pnpm test:web        # Web unit tests (Vitest, single run)

# From apps/web
pnpm test            # Vitest watch mode
pnpm test:run        # Vitest single run (what test:web calls)
pnpm test:e2e        # Playwright E2E
```

## Boundary between layers

- **API logic** (formulas, transformations, repository/service behavior) → pytest in `apps/api/tests/`.
- **Web pure functions** (formatting, locale/i18n helpers, parsers) → Vitest in `apps/web/tests/unit/`.
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

## What to test (Web unit)

Vitest, node environment (`apps/web/tests/unit/*.test.ts`):

- **Pure functions only** — the locale/formatting layer (`getLocaleTag`, `formatValue` / `formatAmount`,
  date formatters, the `numeric-input` rule kit + separators), and structural invariants like EN/ES
  translation keyset parity.
- Import from `@/…` exactly as app code does (the `@/*` alias is wired via `vite-tsconfig-paths`);
  import JSON fixtures (e.g. `translations/*.json`) by relative path — the alias plugin does not
  rewrite `.json` imports.
- Assert against manually-computed expected values per locale (e.g. `formatValue(1000, { locale: 'es' })`
  === `'1.000'`) — never by calling the formatter twice.

**Don't unit-test on the web:** React component rendering / hooks (there is no jsdom + React Testing
Library layer today — cover interactive behavior with Playwright E2E instead) or framework behavior.

## File structure

```
apps/api/tests/
├── unit/           # no real DB: pure functions, mocked-session services, in-process TestClient
└── integration/    # live-DB only (env-gated; skipped by default)

apps/web/tests/
├── unit/           # Vitest (node): pure functions — locale/formatting layer, keyset parity
└── e2e/            # Playwright (see the e2e-testing skill)
```

There is no shared `conftest.py` — API tests build their own fixtures/mocks per file.

## Fixtures

- Use `pytest-asyncio` for async services/routes.

## Assertions

- Test the formula result with known inputs and manually computed expected values — don't test by calling the formula twice
- For currency conversion: use hardcoded exchange rates in fixtures, not live API calls
