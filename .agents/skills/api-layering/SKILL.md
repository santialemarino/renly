---
name: api-layering
description: Backend API structure and where to create files (routers, services, repositories, schemas, domain, utils, helpers). Use when adding endpoints, new features, or organizing code in apps/api.
---

# API layering (Renly backend)

## Flow and layers

Request flow: **router → service → repository → DB**.

- **routers/** — HTTP only: validate body, call service, return response or raise HTTPException. Use **schemas** for request/response.
- **services/** — Business logic: orchestrate use cases, call repositories. Use **domain** types and **models**; no HTTP or raw SQL. Owns the transaction boundary (`session.commit()` once per use case).
- **repositories/** — Data access: run queries, `session.add()` / `session.flush()`. Use **models**, the session, and the **domain** value types that shape a query or a row (`ListScope` in five repositories and `repositories/utils.py`, the `AccountMovement` row types in `account_movement_repository.py`). Never call `session.commit()` — the service commits.
- **schemas/** — Pydantic request/response DTOs (HTTP contract). Request bodies inherit from `RequestBase` (`schemas/base.py`) which auto-strips strings and converts empty optionals to `None`. Response schemas inherit from `BaseModel`.
- **domain/** — Types services work with (value objects, enums, errors, specs). Not HTTP. It MAY import **models**: mostly the `StrEnum`s the tables declare (`Currency`, `ExpenseCategory`, `NotificationEvent`, …), and `restore_specs.py` binds each restore spec to its model class (`import_specs.py` imports only those enums). It never imports repositories, services, schemas or routers.
- **models/** — SQLModel tables (DB entities).
- **deps/** — FastAPI dependencies (`SessionDep` and its two privileged siblings, `CurrentUser`, `PageQuery`, the currency param). Injected by the framework.

The two edges into **domain** above (`domain` → `models`, `repositories` → `domain`) are deliberate: an enum is declared once, on the table that stores it, and a query-shaping value object is shared by the service that builds it and the repository that applies it. Do not "fix" them by copying the enum or the value object.

Do not put business logic in routers or SQL in services. Do not put HTTP types (request/response bodies) in domain or models.

## Transaction rules

### Repositories do NOT commit

Repositories call `session.add()` and optionally `session.flush()` (to get generated IDs), but **never `session.commit()`**. The commit happens at the **service level** — one commit per use case. This makes multi-step operations atomic by default.

### Multi-step operations must be atomic

If a service function does multiple writes (e.g., create collection + set members), they must all succeed or all fail. With repository-level commits removed, a single `session.commit()` at the end of the service function achieves this. If an error occurs, the session rolls back on exit.

### Rollback is handled by the session teardown

Services do NOT need try/except + `session.rollback()` around writes. The session dependency
(`app/db.py get_session`) yields from `async with AsyncSessionLocal() as session:` — when the
request scope exits (normally or via an exception), the `async with` closes the session, which
rolls back any transaction that was never committed. So an error raised before the service's
`session.commit()` persists nothing, and the connection returns to the pool clean. An explicit
`session.rollback()` is only warranted when a service wants to recover mid-request and continue
issuing queries on the same session after a failed write.

## Which session a route takes

`app/deps/db.py` declares three, and the choice is a security decision, not a pooling detail:

- **`SessionDep`** — the request session: connects as `renly_app`, which is subject to Row-Level
  Security, and `get_current_user` stashes the user id on it so every transaction runs as that user.
  **Every user-scoped route uses this one.** The policies the database half of a rule is written in
  (below) apply only here.
- **`AdminSessionDep`** — `renly_admin`, which has `BYPASSRLS`: no policy applies to anything it reads
  or writes. Only for authenticated work that must see across users — the admin surface, creating a
  group or a pot and claiming an invite (the caller is not a member yet), reading the admin emails to
  notify, account cleanup. Reaching for it on ordinary request work silently switches off every policy,
  and no test fails, so take it in ADDITION to `SessionDep` and use it only for the cross-user read or
  write that needs it (as `routers/feedback.py` does).
- **`AuthSessionDep`** — also `renly_admin`, on its own small pool, reserved for the pre-auth paths
  (login, register, refresh, verification, password reset, invite preview, API-key verification) so a
  scheduler job holding the admin pool can never queue a login. `tests/unit/test_auth_pool_routing.py`
  derives the routes from the app and fails when a pre-auth route or a user resolver reads the admin
  pool, or an authenticated route works on the auth pool.

## Rate limits

`app/rate_limit.py` is the whole surface: one slowapi `Limiter` keyed by user id when a valid bearer
token is present and by client IP otherwise (`client_ip` honours `TRUSTED_PROXY_COUNT`, and the
`X-Renly-Client-IP` the web server sends on its own calls when `INTERNAL_API_SECRET` matches), a global
`DEFAULT_LIMIT` that `SlowAPIMiddleware` applies to every route, and named constants for the tighter
per-route limits (`LOGIN_LIMIT`, `REGISTER_LIMIT`, the email-sending routes, `IMPORT_LIMIT`,
`RESTORE_LIMIT`, `EXPORT_LIMIT`, `FEEDBACK_LIMIT`, `INVITE_LIMIT`). A new limit is a constant there,
applied with `@limiter.limit(<CONSTANT>)` under the route decorator; `@limiter.exempt` is for probes
(`/health`). A 429 is the generic `rate_limit_exceeded_handler` body with `Retry-After`.

**The gotcha:** every `@limiter.limit` endpoint must declare BOTH `request: Request` and
`response: Response` parameters, even when it uses neither. slowapi finds the request by that
parameter NAME and refuses to decorate a function without one; and with `headers_enabled` it writes
the `X-RateLimit-*` headers into the `response` parameter on the success path, so an endpoint that
returns a Pydantic model and declares no `response` raises at request time. The limiter's counters are
in-process state shared by every test: a test that drives a limited route resets it first
(`limiter.reset()`, as `tests/unit/test_perimeter_hardening.py` does).

## Error responses (codes, not localized prose)

The backend stays **locale-agnostic**: it returns a stable machine `code` per error and an English
`detail` (dev/fallback); the frontend maps `code` → a localized message. (Transactional emails are
the one backend-localized exception — no frontend renderer.)

- **Domain errors** (`app/domain/errors.py`) subclass `DomainError` and set a class-level `code`
  (stable, unique kebab/snake string) and `status_code`; the constructor assigns `self.message`.
  Errors that carry structured data override the `extra` property (e.g. `{"fields": [...]}`). A
  single handler in `app/main.py` turns any `DomainError` into `{"detail", "code", **extra}` — do
  NOT add a per-error handler. Raise domain errors from services; the router just lets them bubble.
- **Ad-hoc HTTP errors** raised in routers / deps / middleware (login, admin gate, request-too-large,
  a param-validation 400) use `CodedHTTPException(status_code, detail, code)` (`app/http_errors.py`)
  so they join the same `{detail, code}` contract; a plain `HTTPException` stays `{detail}` (the
  frontend falls back to it). Prefer a domain error when the condition is a domain rule.
- Reuse an existing `code` when the condition is the same across sites (e.g. login and re-auth both
  use `invalid_credentials`), so the frontend maps it once.
- Every code the API can send, from any source above (or a hand-built `JSONResponse` body such as the
  IntegrityError handler's), needs an `apiErrors.<code>` in BOTH `en.json` and `es.json`:
  `apps/web/tests/unit/api-error-coverage.cross-app.test.ts` scans all of `app/` for them. Pass a code
  as a string literal or a module-level string constant so the scan can read it; any other expression
  in a `code=` / `"code":` position fails the test until it is pinned there with a reason.
- **Success responses** don't carry localized prose either — the frontend owns success copy per
  action. Give a success ack a machine field only when a caller must branch on it (e.g. a token type).

### A rule the database has to hold too

Where a service rule also exists as a row-level policy, the two are one rule in two languages and the
database is the one that cannot be bypassed. Three facts decide how to write the SQL half, each
non-obvious and each silent when wrong:

- **Split a policy per COMMAND when the verbs differ.** `FOR ALL` grants SELECT, INSERT, UPDATE and
  DELETE on one predicate, which is almost never what a table wants — a ledger that is inserted and
  deleted but never edited should say so, so a later `UPDATE` is refused by the database rather than by
  nobody. Note Postgres has no `WITH CHECK` for DELETE, so a `FOR ALL` whose `USING` is the read
  predicate silently lets a read-only caller delete.
- **A `FOR UPDATE` policy with no `WITH CHECK` reuses its `USING` expression as the check.** So the row
  must qualify both before and after either way, and spelling the predicate twice is duplication that
  can never disagree — write `USING` alone.
- **RLS filters ROWS and never COLUMNS.** A policy cannot say "you may write this column and no other";
  only `REVOKE UPDATE ON <table>` plus `GRANT UPDATE (<column>)` can. The difference is visible at
  runtime: a policy refuses by returning "nothing changed", a grant refuses with a permission error.
  Grant the narrowest column set that is actually written — a column a trigger maintains needs no grant,
  because column privileges are checked against the statement's own SET list. "Actually written" means
  by EVERY path, including one that re-points a denormalized child when its parent changes scope: the
  check runs per statement, so a statement naming an ungranted column is refused even when it matches no
  row. `tests/integration/test_update_column_privileges.py` derives the application's writes and fails
  on any the grant does not cover.

And the discipline that keeps the pair honest: **prove a clause is load-bearing by constructing the row
that would need it** and watching which layer refuses. A clause that looks subsumed by a helper often is
not, and a clause that genuinely is may still be worth keeping — but say which, in a comment, so nobody
reads a redundant guard as the one doing the work.

### One refusal rule when a picker and a write must agree

Where a surface OFFERS a set of things and a write then refuses some of them, the offer and the refusal
are the same rule and must be one function — otherwise every condition is a chance for the two to
disagree, and each disagreement is a row the user picks and is then refused for.

Write it as a function that **RETURNS** the domain error (or `None`) rather than raising:

```python
# Why this row cannot be used, or None when it can. The write RAISES it, the list FILTERS on it.
def contribution_refusal(row, base_currency, price) -> Exception | None:
    if row.value is None:
        return PotHoldingUnvaluedError()
    ...
    return None
```

The write does `refusal = rule(...)`, `if refusal is not None: raise refusal`; the list read does
`[row for row in rows if rule(row, ...) is None]`. Two consequences to keep:

- **Any guard the list cannot express as a filter has to be excluded some other way**, and the list's
  own comment should say which group each condition falls into and count them — a "seven conditions,
  all seven filtered" claim is checkable, "we filter the important ones" is not.
- **A guard that raises about a whole batch cannot be reused by a picker.** An existence check
  (`exists_for_accounts -> bool`) answers about the set, so a picker built on it drops every candidate
  the moment one qualifies. Return the offending ids instead and put the raising wrapper on top; the
  enumeration then lives in exactly one place.

## Currency conversion (services own it)

Display-currency conversion is a service-layer concern. Routers never read the dollar
preference, never build rate lookups, and never convert values — they pass the `currency`
query param through and return the schema the service built.

- `exchange_rate_service.get_user_rate_lookup(session, user_id)` is the single entry point:
  it reads the user's dollar-rate preference and returns a `RateLookup` pre-loaded with every
  stored rate. Build **one per request** and pass it down to composed service calls via their
  `lookup=` parameter — never build a second lookup for the same request.
- `app/utils/metrics.py` stays pure (no DB): `RateLookup` (data structure), `convert_value`,
  `convert_optional`, `can_convert`.
- Per-row converted response fields use `convert_optional(value, from_currency,
target_currency, lookup, as_of_date)` — historical rows (expenses, income, calendar items)
  convert at their own date; current-state rows (plans, card balances) at today's.

## Performance rules

### Never query inside a loop (N+1)

If you need data for N items, fetch it in **one batch query** before the loop, then look up from a dict/set. Never call a repository method inside a `for` loop.

```python
# BAD — N+1: one query per collection
for c in collections:
    ids = await collection_repository.get_investment_ids_by_collection(session, c.id)

# GOOD — batch load, then loop in memory
ids_by_collection = await collection_repository.get_investment_ids_by_collections(session, [c.id for c in collections])
for c in collections:
    ids = ids_by_collection.get(c.id, [])
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

### Chunk an `IN` whose list is not bounded by one user

asyncpg refuses a statement carrying more than 32,767 bind parameters, and `column.in_(ids)` binds one per id. A
repository read whose id list grows with the user base — anything the scheduler reaches, or a fan-out over every
pot a household holds — loops `for chunk in chunked(ids):` (`app/repositories/utils.py`) and merges the results.
A list drawn from one request's own rows stays a single `IN`. `tests/unit/test_in_chunking.py` derives every
repository `IN` over a caller list and fails until a new one is chunked or named bounded with a reason.

### Every list endpoint is bounded — paginated, capped, or BOUNDED with a reason

`tests/unit/test_list_endpoint_bounds.py` reads every mounted GET route whose response model is a list,
carries an `items` field, or is opaque (a bare dict, `Any`, no model), and requires it in exactly one of
three buckets — so a new list endpoint fails until you classify it there:

- **`PAGINATED`** — a list that grows with time (a ledger, a history, an admin list across users). Take
  the window from the shared `PageQuery` dependency (`app/deps/pagination.py`; never declare
  `page` / `page_size` inline — the test checks the dependency's provenance, not just the values),
  return a schema that inherits `PaginatedResponse` (`total`, `page`, `page_size`) and declares its own
  `items`, and apply it with `apply_page`
  (`app/utils/pagination.py`) on a TOTAL order (add an id tiebreak). Defaults are pinned:
  `DEFAULT_PAGE_SIZE` 25, `MAX_PAGE_SIZE` 100, `MAX_PAGE` 1,000,000 — over either ceiling is a 422.
- **`CAPPED`** — a list bounded by what the user chose to create (accounts, cards, collections, pots).
  Pass `limit=MAX_LIST_ROWS` (500) from the list endpoint's call site ONLY, apply it with
  `apply_limit`, and route the rows through `capped(rows, limit, what)`, which logs when the ceiling
  bites. The same query unbounded (`limit=None`) is what the dashboard SUMS, so never default the cap
  inside the repository. The test drives each capped endpoint and requires a SELECT carrying
  `LIMIT 500`; `tests/unit/test_repository_namespaces.py` fails on a read that applies a limit without
  `capped(`.
- **`BOUNDED`** — neither, with the REASON written as the dict value (a computed list of constant
  length, the export that is unbounded by contract). This is where an unbounded read would hide, so
  the reason is the price of entry.

`tests/integration/test_list_bounds_queries.py` seeds past each bound against Postgres.

### Use bulk upserts for batch writes

When storing multiple rows (prices, exchange rates, ratios), prefer PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` over individual SELECT + INSERT/UPDATE loops. Use `sqlalchemy.dialects.postgresql.insert` for this.

### Prefer higher-order operations over manual loops

Use `sum()`, `max()`, `min()`, list comprehensions, and generators instead of manual accumulator loops when the intent maps naturally. Use a `for` loop only when you need early `break`, `async` iteration, side effects per iteration, or it's genuinely clearer.

## Where to create files

- **New feature (e.g. investments):** add one file per layer: `routers/investments.py`, `services/investment_service.py`, `repositories/investment_repository.py`, `schemas/investment.py`, and optionally `domain/investment.py`.
- **New endpoint in existing feature:** add the route in the existing router; add service/repository functions in the existing service/repository files. Split into a new file only when a file gets too large or the domain is clearly separate.

### A repository's namespace registry

A repository file is module-level `async def` queries plus a `<Entity>Repository` class that re-exports
each one as `name = staticmethod(name)`, and a singleton of that class (`feedback_repository =
FeedbackRepository()`) is what services import — most are also re-exported, alphabetically, from
`app/repositories/__init__.py` (not every one yet: `feedback_repository` is imported from its module). **A new public `async def` is not reachable until its
`staticmethod` line is added**: the module imports fine and `pnpm check:api` passes, and the first
service call is an `AttributeError`. `tests/unit/test_repository_namespaces.py` parses every
`*_repository.py` and fails on a public `async def` missing from its class (and on a file without the
class). Private `_helpers` and synchronous SQL-expression builders (`sort_columns`,
`settlement_cash_leg`) stay off the registry; callers import those directly.

## External data providers

External data fetching (prices, exchange rates) uses a standardized provider pattern. See `docs/technical/external-providers.md` for the full spec. Key points:

- **Provider files** (`services/price_providers.py`, `services/exchange_rate_providers.py`) own all external logic: URLs, HTTP calls, response parsing.
- **Services** map categories to providers and handle storage — zero provider-specific code.
- All providers of the same type share a **uniform function signature** and return type.
- To swap or add a provider, change the mapping. No service or router changes needed.

## Utils vs helpers

- **utils** — General-purpose, not tied to one entity or service. Used across multiple services or the app.
  - **Where:** `app/utils/` (e.g. `app/utils/dates.py`, `app/utils/pagination.py`, `app/utils/metrics.py`). If only used by one layer, `app/<layer>/utils.py` (`app/services/utils.py`, `app/repositories/utils.py`, `app/models/utils.py`).
- **helpers** — Tied to a specific service or entity (e.g. auth, user, investment).
  - **Where:** next to the code that uses it, as `app/services/<feature>_helpers.py` beside its service (none exists today; most feature helpers are private `_functions` inside the service, and a few feature-adjacent modules carry a more specific name, such as `email_templates.py` beside `email_service.py`). Prefer a single file per feature rather than a generic "helpers" folder.

Rule: if it's used by one service/entity only → **helper** file next to that feature. If it's generic and reusable across features → **utils** (under `app/utils/` or under the layer if layer-scoped).

## Order in **init** and multi-export files

In every `__init__.py` or file that imports/exports multiple symbols (e.g. singletons like `user_repository`, `investment_repository`), list them **alphabetically** (imports and `__all__`). Exception: when a specific order is explicitly defined for a specific file (that order will be defined in this skill), follow that order instead.

## Directory layout (apps/api/app/)

```
app/
├── config.py
├── db.py            # the three engines and session factories (see "Which session a route takes")
├── http_errors.py   # CodedHTTPException
├── main.py
├── middleware.py
├── observability.py
├── rate_limit.py    # the limiter and every limit constant
├── scheduler.py
├── deps/
├── domain/          # domain/<feature>.py
├── models/
├── repositories/    # <entity>_repository.py
├── routers/        # <feature>.py
├── schemas/        # <feature>.py
├── services/       # <feature>_service.py
└── utils/          # general-purpose
```

## Schema ↔ migration parity

A schema change lands in BOTH `apps/api/database/01_create_tables.sql` (the canonical rebuild-from-zero
script) and a new Alembic migration, in the same change (`agent-workflow` §4 has the why). What holds the
two together:

- **CI replays the chain.** `ci.api.yml` builds the baseline schema (the SQL file as it stood when
  Alembic was adopted, stamped `0001_baseline`), upgrades it through the whole chain — online, and again
  as the script `alembic upgrade --sql` writes — and fails when either result's schema differs from the
  one the current SQL file builds. So a migration must also work offline: a migration
  that reads the database decides inside one SQL statement (a `DO` block), never through
  `op.get_bind()`.
- **Functions are byte-identical.** For every function the schema file defines that some migration
  also defines, `tests/unit/test_schema_parity.py` requires the schema file's body to appear verbatim in
  a migration; pg_dump reproduces a body exactly, so a re-indented copy is a real difference. A function
  only the schema file defines (`set_updated_at`) is outside that test; the CI chain replay above is
  what catches a missing migration copy. The same file pins which tables are
  policied, FORCEd and split per command, and the global reference tables that are not.
- **Enums have twins.** A new `StrEnum` fails `tests/unit/test_enum_parity.py` until it is paired with
  its web list or declared server-only; a new `notification_event` label must be added by a migration in
  the order `tests/unit/test_notification_event_surface.py` replays.
- **Naming.** Every migration is `migrations/versions/NNNN_<slug>.py` — the next four-digit number, a
  short snake_case slug — with `revision` equal to the file's stem and `down_revision` equal to the
  previous file's stem (`0032_recon_follows_account` revises `0031_recon_scope_grant`). `migrate:make`
  autogenerates a random hex id and a hex-prefixed filename, so rename the file and set both ids before
  committing. `tests/unit/test_migration_names.py` fails on a misnamed file, a `revision` that is not
  its stem, a `down_revision` that is not the previous file's, a gap in the numbers or a second head —
  the chain must stay linear and number-ordered because `test_notification_event_surface.py` reads the
  migrations in filename order as the order Alembic applies them, and CI stamps the baseline by its id
  (`0001_baseline`).
- **Roles and definer functions** follow `apps/api/README.md` → Migrations;
  `tests/integration/test_rls_force_role_model.py` fails until a new `SECURITY DEFINER` function is
  handed to `renly_policy_definer`.
