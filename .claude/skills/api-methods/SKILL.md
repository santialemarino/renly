---
name: api-methods
description: How to create and order methods in routers, services, repositories; how to document them and types with comments. Use when adding or reviewing API code in apps/api.
---

# API methods and documentation (Renly backend)

## Method order

**Repository:** (1) Get methods — general first (e.g. list, get_many), then by id or by key (get_by_id, get_by_email). (2) create. (3) update / save. (4) delete. After that, any other methods in the neatest order possible.

**Service:** Same as repository when it’s CRUD. When it’s a flow (e.g. get_dashboard_context → get_snapshot → add_transaction), order methods in that flow order. Provider- or entity-specific methods after the general (e.g. get_investment_with_snapshots after get_investment_by_id).

**Routers:** Same as repository when it’s CRUD. Order endpoints by flow when there is one (e.g. get context → get snapshot → process). Otherwise: list/context, get by id, create, update, delete. Provider- or entity-specific endpoints after the general.

## Pattern per layer

- **Router:** Validate body (schemas), call service, return response or raise HTTPException. No business logic, no DB.
- **Service:** Orchestrate use case, call repository; pure functions for crypto/validation. No HTTP, no raw SQL.
- **Repository:** Session + model only: queries, add, commit, refresh. No business rules.

## Comments

Use **`#`** block comments **above** the definition (no docstrings inside).

- **Router:** 1–2 lines above `@router.*` — what the endpoint does; optional "Returns …" or error status.
- **Service:** 1–2 lines above `def` — what it does; optional "Returns: …".
- **Repository:** 1–2 lines above `async def` — what it does; optional "Returns: …".
- **Schemas:** One `#` above each class (endpoint/role). Every field: `Field(description="...")`.
- **Domain/Models:** `#` above class only when the role isn’t obvious.

One or two lines per comment. No docstrings in the function body.
