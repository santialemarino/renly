---
name: testing
description: Where tests live, how to run them, and what to test in the Renly repo. Use when writing or running tests.
---

# Testing (Renly)

## Current state

- **API tests:** `apps/api/tests/unit/` — pytest, ~850 tests across ~50 files covering metrics/date/liquidity helpers, service flows (mocked sessions/repos), schema validation, and in-process endpoint behavior.
- **Web unit tests:** `apps/web/tests/unit/` — Vitest, split into two projects by file extension (`apps/web/vitest.config.ts`): a **`node`** project for `*.test.ts` (pure functions — the locale/formatting layer under `lib/i18n/`, the `numeric-input` rule kit, EN/ES keyset parity) and a **`jsdom`** project for `*.test.tsx` (React components/hooks driven with React Testing Library + `@testing-library/user-event`, e.g. `LocaleAmountInput`). `vite-tsconfig-paths` wires the `@/*` alias; the jsdom project loads `tests/setup-jsdom.ts` (jest-dom matchers + RTL cleanup). Run both with `pnpm test:web`.
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
- **Web pure functions** (formatting, locale/i18n helpers, parsers) → Vitest `node` project (`*.test.ts`) in `apps/web/tests/unit/`.
- **Web component/hook behavior** (stateful inputs, effects, caret/DOM logic) → Vitest `jsdom` project (`*.test.tsx`) with React Testing Library, in `apps/web/tests/unit/`.
- **User-facing flows** (login, transactions, dashboard render, navigation) → Playwright E2E in `apps/web/tests/e2e/`. See `e2e-testing` for specifics.

## What to test (API)

**Unit test** (`tests/unit/` — no real database):

- Pure calculation/transformation functions in `services/` or `utils/` (formulas, parsers, date math).
- Service flows with mocked sessions/repositories (`unittest.mock.AsyncMock`, `monkeypatch`).
- Endpoint behavior driven **in-process** (FastAPI TestClient / ASGI transport with overridden
  dependencies — auth, session). These still count as unit tests: no network, no Postgres.

**Integration test** (`tests/integration/` — a live database):

- Tests that need a real Postgres (schema, roles, RLS), each gated on its own env var and skipped
  when unset, so the default `pnpm test:api` run stays green without a DB. Today:
  - `test_rls_isolation.py` — `RLS_TEST_DATABASE_URL` + `RLS_TEST_ADMIN_DATABASE_URL`.
  - `test_account_ledger_drift.py` — `LEDGER_TEST_DATABASE_URL`.
  - `test_group_lifecycle.py` — `GROUPS_TEST_DATABASE_URL` (owner role only).
  - `test_rls_pot_scope.py` — the same two `RLS_TEST_*` vars as `test_rls_isolation.py`, so the two
    run together. Covers the dual-scope policies, whose service layer holds a second copy of the
    same rules — the failure that matters is the two disagreeing, which only a real policy shows.
  - `test_snapshot_scope_queries.py` — `LEDGER_TEST_DATABASE_URL` (owner role only). Query
    semantics, not visibility: an aggregate bounded before rather than after its filter, and a
    bulk insert whose omitted column only a CHECK constraint rejects.
  - `test_pot_holdings_query.py` — `LEDGER_TEST_DATABASE_URL` (owner role only). The pot-holdings
    read, whose two properties are decisions rather than accidents: it is NOT filtered on
    `is_active` where the two NAV queries beside it are (an archived holding still blocks deleting
    the pot and still has to be movable out), and it IS filtered by `pot_id` (one pot must never
    read another's, nor a private holding). Both live entirely in the SQL.
  - `test_pot_ownership_delete.py` — `LEDGER_TEST_DATABASE_URL` (owner role only). The
    baseline-deletion statement, a `DELETE … WHERE` whose two predicates each fail differently:
    without `type = 'opening'` it takes the pot's contributions and withdrawals too, and without
    `pot_id` it takes every OTHER pot's baseline in the database. Seeded with two pots so a
    too-wide predicate shows up as a deletion somewhere it was not asked for.
- **Reach for one when the same fact is stated in two queries.** A unit test mocks repositories, so
  it cannot notice that two SQL statements which must describe the same row set have stopped
  agreeing — it will happily pass on both the right answer and the wrong one. Assert the two against
  a real database instead, and prove the guard fails when you break one of them on purpose.
- **Reach for one when a query DECIDES something destructive.** A correlated `EXISTS` / `NOT EXISTS`
  pair, a `DELETE … WHERE`, or any predicate whose wrong answer removes a row rather than merely
  hiding one cannot be validated by a mocked session at all — the mock returns whatever it was told
  to. Drive the real repository function against a real database, cover the near-miss cases (not only
  the ones that obviously qualify), and break the predicate one clause at a time: a case list that
  only contains obvious qualifiers will pass even after a whole clause is deleted.

**Don't test:**

- Framework behaviour (FastAPI routing, SQLModel field types)
- Simple CRUD with no logic (list, get by id, delete)

## What to test (Web unit)

**`node` project — pure functions** (`apps/web/tests/unit/*.test.ts`):

- The locale/formatting layer (`getLocaleTag`, `formatValue` / `formatAmount`, date formatters, the
  `numeric-input` rule kit + separators + grouping/caret helpers), and structural invariants like
  EN/ES translation keyset parity.
- Import from `@/…` exactly as app code does (the `@/*` alias is wired via `vite-tsconfig-paths`);
  import JSON fixtures (e.g. `translations/*.json`) by relative path — the alias plugin does not
  rewrite `.json` imports.
- Assert against manually-computed expected values per locale (e.g. `formatValue(1000, { locale: 'es' })`
  === `'1.000'`) — never by calling the formatter twice.

**`jsdom` project — component/hook behavior** (`apps/web/tests/unit/*.test.tsx`):

- Render with `@testing-library/react` and drive with `@testing-library/user-event`; assert the DOM
  the user sees (input `value`, caret via `selectionStart`, `aria-*`) and the values a controlled
  component emits via `onChange`. Reserve this for genuinely stateful/DOM-coupled logic that pure
  helpers can't cover (e.g. `LocaleAmountInput`'s live grouping + caret, resync/precision effects) —
  extract and node-test the pure parts first.
- Components that read locale/timezone render under a `NextIntlClientProvider` (pass `locale` +
  `messages={{}}` + `timeZone`); a controlled input needs a small stateful harness that feeds
  `onChange` back as `value`. Prefer `keyboard` + a manual `setSelectionRange` over `type` when a
  test needs the caret at a specific position.

**Don't unit-test on the web:** framework behavior, or full multi-page user flows (those are Playwright
E2E). Keep a jsdom test to a single component's behavior.

## File structure

```
apps/api/tests/
├── unit/           # no real DB: pure functions, mocked-session services, in-process TestClient
└── integration/    # live-DB only (env-gated; skipped by default)

apps/web/tests/
├── unit/           # Vitest — *.test.ts on node (pure functions), *.test.tsx on jsdom (components, RTL)
├── setup-jsdom.ts  # jsdom project setup: jest-dom matchers + RTL cleanup
└── e2e/            # Playwright (see the e2e-testing skill)
```

There is no shared `conftest.py` — API tests build their own fixtures/mocks per file.

## Fixtures

- Use `pytest-asyncio` for async services/routes.

## Assertions

- Test the formula result with known inputs and manually computed expected values — don't test by calling the formula twice
- For currency conversion: use hardcoded exchange rates in fixtures, not live API calls
