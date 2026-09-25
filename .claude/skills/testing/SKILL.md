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
  - `test_group_lifecycle.py` — `GROUPS_TEST_DATABASE_URL` (the BYPASSRLS admin role, `renly_admin`).
  - `test_rls_pot_scope.py` — the same two `RLS_TEST_*` vars as `test_rls_isolation.py`, so the two
    run together. Covers the dual-scope policies, whose service layer holds a second copy of the
    same rules — the failure that matters is the two disagreeing, which only a real policy shows.
  - `test_snapshot_scope_queries.py` — `LEDGER_TEST_DATABASE_URL` (the BYPASSRLS admin role, `renly_admin`). Query
    semantics, not visibility: an aggregate bounded before rather than after its filter, and a
    bulk insert whose omitted column only a CHECK constraint rejects.
  - `test_pot_holdings_query.py` — `LEDGER_TEST_DATABASE_URL` (the BYPASSRLS admin role, `renly_admin`). The pot-holdings
    read, whose two properties are decisions rather than accidents: it is NOT filtered on
    `is_active` where the two NAV queries beside it are (an archived holding still blocks deleting
    the pot and still has to be movable out), and it IS filtered by `pot_id` (one pot must never
    read another's, nor a private holding). Both live entirely in the SQL.
  - `test_pot_ownership_delete.py` — `LEDGER_TEST_DATABASE_URL` (the BYPASSRLS admin role, `renly_admin`). The
    baseline-deletion statement, a `DELETE … WHERE` whose two predicates each fail differently:
    without `type = 'opening'` it takes the pot's contributions and withdrawals too, and without
    `pot_id` it takes every OTHER pot's baseline in the database. Seeded with two pots so a
    too-wide predicate shows up as a deletion somewhere it was not asked for.
  - `test_rls_shared_flows.py` — the same two `RLS_TEST_*` vars. The membership policies on the
    shared-flow tables, and specifically the boundary of the second READ branch two of them carry:
    a FORMER member must still see the rows naming an account or card they own (without it their own
    balance silently gains back money it no longer holds) and must see nothing else, and must not be
    able to DELETE the row they can still read — which one `FOR ALL` policy would let them do,
    because Postgres has no `WITH CHECK` for DELETE.
  - `test_notification_queries.py` — `LEDGER_TEST_DATABASE_URL` (the BYPASSRLS admin role, `renly_admin`). The two
    notification statements whose whole correctness lives in the SQL: the fan-out's
    `ON CONFLICT DO NOTHING` against a PARTIAL unique index (Postgres matches a partial index only
    when the statement repeats its predicate, and getting it wrong raises on every send — invisibly,
    because the dispatcher swallows its own exceptions), and the three feed reads that share one
    WHERE, whose failure is the badge and the list describing different row sets.
  - `test_shared_flow_queries.py` — `LEDGER_TEST_DATABASE_URL` (the BYPASSRLS admin role, `renly_admin`). The three queries
    whose whole correctness lives in the SQL: the `/expenses` UNION (does it return the caller's
    SHARE or the whole expense, and is its page order total across two tables whose ids collide), the
    balance aggregation, and the settlement leg sums' `coalesce(<leg>_amount, amount)`. Seeded with
    one cross-currency settlement whose three figures all differ, so a query reading the wrong column
    shows up as two accounts moving by each other's amount.
  - `test_account_reconciliation_replace.py` — `LEDGER_TEST_DATABASE_URL` (the BYPASSRLS admin role, `renly_admin`). Two
    facts about re-reconciling a date, both of which a mocked session can only watch the ORDER of.
    The `(account_id, as_of_date)` UNIQUE constraint, asserted as a refused INSERT rather than as
    behaviour a code path chooses, because the point is that the two-row state is unreachable for
    every caller. And the preview agreeing with the write: the dialog SUBTRACTS the superseded row's
    difference while the save DELETES it and re-derives, so each case reads the preview, saves, and
    asserts the recorded `computed_balance` is the figure the user was shown.
  - `test_ownership_predicates.py` — `LEDGER_TEST_DATABASE_URL` (the BYPASSRLS admin role, `renly_admin`). Every repository
    keyed read or delete (`get_by_*`, `find_by_*`, `delete_*`) that takes a `user_id` alongside another
    parameter, driven against two users' rows: a read must return the row to its owner AND nothing to
    anybody else, and a delete must remove the named user's rows and nobody else's. The predicate IS the
    behaviour, so a mocked session cannot test it at all — deleting `X.user_id == user_id` from four
    repositories left the whole unit suite green, and the two token deletes run on the admin session,
    where RLS cannot backstop them. Also the two funding rules that ask "does this belong to THAT
    MEMBER", which RLS cannot answer. Its population is DERIVED by
    `tests/unit/test_ownership_predicate_coverage.py`, which fails when a new owner-scoped read or
    delete appears with no case here.
  - `test_list_bounds_queries.py` — `LEDGER_TEST_DATABASE_URL`. The list caps and the pager's
    `OFFSET`, seeded PAST the boundary (`MAX_LIST_ROWS + 1` rows, three pages), because a bound
    asserted against fewer rows than it bounds passes with the bound deleted.
  - `test_pot_balance_series_queries.py` — `LEDGER_TEST_DATABASE_URL`. The dated sums the pot value
    series is built on: the `date <= until` and `date >= opening_date` bounds, the scope predicate on
    pot-scoped transfers (which have no `user_id`), and the per-leg column choice on cross-currency
    movements — all in the SQL, where the unit suite's agreement check cannot reach.
  - `test_pot_contribution_value.py` — `LEDGER_TEST_DATABASE_URL`. Contributing a holding moves
    NOBODY's value — a claim spanning the ledger replay, the NAV sum, the balance union and the share
    split, four of which read SQL.
  - `test_rls_force_role_model.py` — the two `RLS_TEST_*` vars. The role model itself: every policied
    table and every table with a `user_id` / `group_id` / `pot_id` column is ENABLEd and FORCEd
    (derived from the catalogue), the roles carry the attributes the model depends on, the
    `SECURITY DEFINER` helpers are owned by `renly_policy_definer` and it reads only what they read,
    tables a migration creates reach `renly_app` with their grants, and `row_security = off` is the loud
    guard. It also reads a group and a pot as `renly_app` under a NOSUPERUSER owner — directly when the
    database's owner is one, and otherwise by re-owning the owner's objects to a throwaway role inside a
    rolled-back transaction, because a superuser owner hides the defect it pins.
  - `test_rls_reagreement_confirm.py` — the two `RLS_TEST_*` vars. Who may confirm a re-agreement and
    what the confirmation locks: the affected-seat expression and the lock live only in the policy, with
    a second copy in the service that must not disagree with it.
  - `test_rls_shared_audit.py` — the two `RLS_TEST_*` vars. The audit trail's policy (its second,
    pot-visibility branch), the grants that make it append-only while its cascades keep working, and the
    counterparty-delete policy on `pot_ownership_events`.
  - `test_shared_account_reconciliation.py` — the two `RLS_TEST_*` vars. A pot's account becoming
    reconcilable: which row a reconciliation locks (a locking read is governed by the UPDATE policy), who
    may write one, and the column grant that caps what an update may touch.
- **Which role each URL names.** `RLS_TEST_DATABASE_URL` is `renly_app`; every other var, including
  `RLS_TEST_ADMIN_DATABASE_URL`, is `renly_admin` — never the owner, which under FORCE reads nothing when
  it is a NOSUPERUSER and everything when it is a superuser, so neither exercises what the suites assert.
  All four must carry the `postgresql+asyncpg://` prefix. To run the RLS suites production-shaped, build
  the database `OWNER` a throwaway NOSUPERUSER NOBYPASSRLS role: run `apps/api/database/00_roles.sql`
  against it as the superuser, then apply `01_create_tables.sql` as that role.
- **Reach for one when the PREDICATE IS THE BEHAVIOUR.** A repository method whose whole job is a
  `WHERE` clause cannot be tested through a mocked session: the mock returns what the test told it to,
  so the assertion reads the same whether the clause is there or not. Ownership scoping is the
  canonical case — and when several methods share the shape, DERIVE the population from the source
  rather than listing it, or the next one added is unpinned by default.
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
  `messages={{}}` + `timeZone`, or the real `translations/<locale>.json` when the copy itself is the
  thing under test); a controlled input needs a small stateful harness that feeds `onChange` back as
  `value`. Prefer `keyboard` + a manual `setSelectionRange` over `type` when a test needs the caret at
  a specific position.
- **A component that renders a RADIX primitive cannot currently be tested here.** `apps/web` and
  `packages/ui` declare different React ranges, so pnpm installs two copies; `vitest.config.ts`'s
  `dedupe` collapses the direct imports but a transitive dependency reached through `@repo/ui` (Radix)
  still resolves its own, and the render dies with `Cannot read properties of null (reading
'useState')` from inside the Radix component while everything around it renders fine. The message
  points at React, not at the duplication, so it is worth recognising rather than debugging. A
  `resolve.alias` in the vitest config does NOT fix it (tried). Until the two ranges are aligned, test
  such a component's logic through what it renders WITHOUT the primitive, or cover it in the browser.

**Don't unit-test on the web:** framework behavior, or full multi-page user flows (those are Playwright
E2E). Keep a jsdom test to a single component's behavior.

## Two assertions that pass on the failure they exist to catch

- **A translation-parity check must assert the KEY PATH IS ABSENT from the output, never that the result
  is truthy.** next-intl (`createTranslator`, and the app at runtime in production) answers a missing
  message by returning its own key path — a non-empty string — so `expect(t(key)).toBeTruthy()` passes
  on exactly the missing key it was written to find. Assert `expect(t(key)).not.toContain(key)` instead,
  and prove it by deleting a real key.
- **`SELECT … FOR UPDATE` on an RLS table applies the UPDATE policy's USING clause, not the SELECT
  one.** That decides who may take a lock, and it is a live-database fact no unit test can substitute
  for: a path that locks a parent row to serialise itself will work for one role and silently return
  nothing for another. Where a lock is load-bearing, pin the roles that may take it in
  `tests/integration/`, in both directions.

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

`apps/api/tests/unit/conftest.py` holds ONE autouse guard and nothing else: it fails any unit test
that opened a real privileged session. Every service takes its session from the caller, which is what
makes the unit suite DB-free by construction — `notification_service` is the one exception, and two of
its functions open their own, because both do something no request connection may: `dispatch` writes
rows for OTHER users into a table with no INSERT policy, and `subscribe_push` detaches a browser from
whichever account held it before. A unit test reaching either would connect to whatever
`DATABASE_ADMIN_URL` names, which on a developer's machine is their real data, and `dispatch` would do
so silently (it swallows every exception). The guard therefore records rather than raises, and asserts
at TEARDOWN, because a raise inside dispatch is exactly what dispatch ignores. Reaching it usually
means a producer was driven without stubbing `notification_service.dispatch` — which is also what lets
a test assert WHAT was announced.

Apart from that guard, API tests build their own fixtures/mocks per file.

## Fixtures

- Use `pytest-asyncio` for async services/routes.

## Assertions

- Test the formula result with known inputs and manually computed expected values — don't test by calling the formula twice
- For currency conversion: use hardcoded exchange rates in fixtures, not live API calls
