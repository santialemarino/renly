---
name: testing
description: Where tests live, how to run them, and what to test in the Renly repo. Use when writing or running tests.
---

# Testing (Renly)

## Current state

- **API tests:** `apps/api/tests/` — pytest. No tests written yet; the folder exists.
- **Web tests:** None planned for MVP.
- **Priority:** The metrics service (period return, TWR, IRR) is the first area that needs unit tests — pure calculation functions, easy to test, high risk if wrong.

## Running tests

```bash
# From apps/api
uv run pytest

# From repo root
pnpm test   # runs turbo test (currently no-ops until tests exist)
```

## What to test (API)

**Unit test** (no DB, no HTTP):

- `services/metrics_service.py` — period return formula, TWR chain, IRR/XIRR, portfolio aggregates
- Any pure calculation or transformation function in `services/` or `utils/`

**Integration test** (real DB or mock session):

- Router + service + repository flows — only for critical paths (e.g. snapshot upsert, transaction side effects)
- Use a test DB (separate `DATABASE_URL`), not mocks — mocks have caused divergence issues before

**Don't test:**

- Framework behaviour (FastAPI routing, SQLModel field types)
- Simple CRUD with no logic (list, get by id, delete)

## File structure

```
apps/api/tests/
├── conftest.py          # pytest fixtures (DB session, test client, factory helpers)
├── unit/
└── integration/
```

## Fixtures

- Define a `test_db` session fixture in `conftest.py` that creates a fresh schema per test run
- Define factory helpers (e.g. `make_investment`, `make_snapshot`) to keep test setup readable
- Use `pytest-asyncio` for async routes/services

## Assertions

- Test the formula result with known inputs and manually computed expected values — don't test by calling the formula twice
- For currency conversion: use hardcoded exchange rates in fixtures, not live API calls
