---
name: api-layering
description: Backend API structure and where to create files (routers, services, repositories, schemas, domain, utils, helpers). Use when adding endpoints, new features, or organizing code in apps/api.
---

# API layering (Renly backend)

## Flow and layers

Request flow: **router → service → repository → DB**.

- **routers/** — HTTP only: validate body, call service, return response or raise HTTPException. Use **schemas** for request/response.
- **services/** — Business logic: orchestrate use cases, call repositories. Use **domain** types and **models**; no HTTP or raw SQL. Owns the transaction boundary (`session.commit()` once per use case).
- **repositories/** — Data access: run queries, `session.add()` / `session.flush()`. Use **models** and session only. Never call `session.commit()` — the service commits.
- **schemas/** — Pydantic request/response DTOs (HTTP contract). Request bodies inherit from `RequestBase` (`schemas/base.py`) which auto-strips strings and converts empty optionals to `None`. Response schemas inherit from `BaseModel`.
- **domain/** — Types used by services only (value objects, enums, errors). Not HTTP, not DB.
- **models/** — SQLModel tables (DB entities).
- **deps/** — FastAPI dependencies (e.g. SessionDep, CurrentUser). Injected by the framework.

Do not put business logic in routers or SQL in services. Do not put HTTP types (request/response bodies) in domain or models.

## Transaction rules

### Repositories do NOT commit

Repositories call `session.add()` and optionally `session.flush()` (to get generated IDs), but **never `session.commit()`**. The commit happens at the **service level** — one commit per use case. This makes multi-step operations atomic by default.

### Multi-step operations must be atomic

If a service function does multiple writes (e.g., create group + set members), they must all succeed or all fail. With repository-level commits removed, a single `session.commit()` at the end of the service function achieves this. If an error occurs, the session rolls back on exit.

### Explicit rollback on write errors

Wrap write operations in try/except and call `session.rollback()` before re-raising. This prevents the session from being left in a broken state.

## Performance rules

### Never query inside a loop (N+1)

If you need data for N items, fetch it in **one batch query** before the loop, then look up from a dict/set. Never call a repository method inside a `for` loop.

```python
# BAD — N+1: one query per group
for g in groups:
    ids = await group_repository.get_investment_ids_by_group(session, g.id)

# GOOD — batch load, then loop in memory
ids_by_group = await group_repository.get_investment_ids_by_groups(session, [g.id for g in groups])
for g in groups:
    ids = ids_by_group.get(g.id, [])
```

When adding a new repository method that will be called in a loop, **always add a batch variant** (accepts a list of IDs, returns a dict keyed by ID).

### Parallelize independent external API calls

When fetching from multiple independent external APIs (e.g., prices for 20 tickers), use `asyncio.gather()` — not a sequential loop. SQLAlchemy async sessions are not thread-safe, so: **parallelize the HTTP fetches, then store results sequentially**.

```python
# BAD — sequential, 20 tickers × 5s = 100s
for inv in investments:
    await fetch_and_store_prices(session, inv.ticker, inv.category)

# GOOD — parallel fetch, sequential store
fetch_results = await asyncio.gather(*[provider.fetch(inv.ticker) for inv in investments])
for inv, results in zip(investments, fetch_results):
    for price_date, price, currency in results:
        await repository.upsert(session, ...)
```

### Use bulk upserts for batch writes

When storing multiple rows (prices, exchange rates, ratios), prefer PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` over individual SELECT + INSERT/UPDATE loops. Use `sqlalchemy.dialects.postgresql.insert` for this.

### Prefer higher-order operations over manual loops

Use `sum()`, `max()`, `min()`, list comprehensions, and generators instead of manual accumulator loops when the intent maps naturally. Use a `for` loop only when you need early `break`, `async` iteration, side effects per iteration, or it's genuinely clearer.

See `docs/backend-performance-audit.md` for the full diagnostic and fix plans.

## Where to create files

- **New feature (e.g. investments):** add one file per layer: `routers/investments.py`, `services/investment_service.py`, `repositories/investment_repository.py`, `schemas/investment.py`, and optionally `domain/investment.py`.
- **New endpoint in existing feature:** add the route in the existing router; add service/repository functions in the existing service/repository files. Split into a new file only when a file gets too large or the domain is clearly separate.

## External data providers

External data fetching (prices, exchange rates) uses a standardized provider pattern. See `docs/external-providers.md` for the full spec. Key points:

- **Provider files** (`services/price_providers.py`, `services/exchange_rate_providers.py`) own all external logic: URLs, HTTP calls, response parsing.
- **Services** map categories to providers and handle storage — zero provider-specific code.
- All providers of the same type share a **uniform function signature** and return type.
- To swap or add a provider, change the mapping. No service or router changes needed.

## Utils vs helpers

- **utils** — General-purpose, not tied to one entity or service. Used across multiple services or the app.
  - **Where:** `app/utils/` (e.g. `app/utils/datetime.py`, `app/utils/validation.py`). If only used by one layer, `app/<layer>/utils.py` or `app/<layer>/utils/<name>.py` (e.g. `app/services/utils.py` for service-wide utils).
- **helpers** — Tied to a specific service or entity (e.g. auth, user, investment).
  - **Where:** next to the code that uses it: `app/services/auth_helpers.py` (used only by auth_service), or `app/repositories/user_repository_helpers.py` if needed. Prefer a single file per feature (e.g. `auth_helpers.py`) rather than a generic "helpers" folder.

Rule: if it's used by one service/entity only → **helper** file next to that feature. If it's generic and reusable across features → **utils** (under `app/utils/` or under the layer if layer-scoped).

## Order in **init** and multi-export files

In every `__init__.py` or file that imports/exports multiple symbols (e.g. singletons like `user_repository`, `investment_repository`), list them **alphabetically** (imports and `__all__`). Exception: when a specific order is explicitly defined for a specific file (that order will be defined in this skill), follow that order instead.

## Directory layout (apps/api/app/)

```
app/
├── config.py
├── db.py
├── main.py
├── deps/
├── domain/          # domain/<feature>.py
├── models/
├── repositories/    # <entity>_repository.py
├── routers/        # <feature>.py
├── schemas/        # <feature>.py
├── services/       # <feature>_service.py
└── utils/          # optional; general-purpose
```
