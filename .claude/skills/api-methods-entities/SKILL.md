---
name: api-methods-entities
description: API method order, comments, and entity conventions (schemas, models, domain). Use when adding or reviewing API code in apps/api.
---

# API methods and entities (Renly backend)

## Method order

**Repository:** (1) Get methods — general first (e.g. list, get_many), then by id or by key (get_by_id, get_by_email). (2) create. (3) update / save. (4) delete. After that, any other methods in the neatest order possible.

**Service:** Same as repository when it's CRUD. When it's a flow (e.g. get_dashboard_context → get_snapshot → add_transaction), order methods in that flow order. Provider- or entity-specific methods after the general (e.g. get_investment_with_snapshots after get_investment_by_id).

**Routers:** Same as repository when it's CRUD. Order endpoints by flow when there is one (e.g. get context → get snapshot → process). Otherwise: list/context, get by id, create, update, delete. Provider- or entity-specific endpoints after the general.

**Another entity / sub-resource:** When a file handles more than one entity (e.g. investments then snapshots), **restart the order for each entity**. So: investments block (list → get → create → update → delete), then snapshots block (list → create → …). Applies to routers, services, and repositories.

## Pattern per layer

- **Router:** Validate body (schemas), call service, return response or raise HTTPException. No business logic, no DB.
- **Service:** Orchestrate use case, call repository; pure functions for crypto/validation. No HTTP, no raw SQL.
- **Repository:** Session + model only: queries, add, commit, refresh. No business rules.

## Schemas (Pydantic)

- Every field: `Field(description="...")`. Optional: `Field(default=None, description="...")`. Str: add `max_length` when relevant; Decimal: `max_digits`, `decimal_places`. Enums: reuse from models (e.g. `Currency`, `InvestmentCategory`).
- Response schemas that map from ORM: `model_config = {"from_attributes": True}`.
- Avoid name clash with types: e.g. `from datetime import date as date_type` if a field is named `date`.

## Models (SQLModel, table=True)

- Set `__tablename__` to snake_case plural. Use `__table_args__` for UniqueConstraint etc. when needed.
- Every field: `Field(...)`. PK: `id: int | None = Field(default=None, primary_key=True)`. FKs: `Field(foreign_key="table.id", description="...")`. Str: `max_length` where relevant. Optional: `Field(default=None)` or `Field(default=True, description="...")`. Timestamps: `Field(default_factory=datetime.utcnow)`. Add `description="..."` for non-obvious columns.

## Comments (routers, services, repositories)

Use **`#`** block comments **above** the definition (no docstrings inside).

- **Router:** 1–2 lines above `@router.*` — what the endpoint does; optional "Returns …" or error status.
- **Service:** 1–2 lines above `def` — what it does; optional "Returns: …".
- **Repository:** 1–2 lines above `async def` — what it does; optional "Returns: …". One `#` above the namespace class (e.g. "Namespace to call repository functions (e.g. investment_repository.list_by_user).") and one above the singleton (e.g. "Singleton used by services to access investment persistence."). Only repositories use this class + singleton pattern; services and routers do not.
- **Schemas:** One `#` above each class describing endpoint/role in one line. Style: "Body for POST /investments.", "Body for PUT /investments/{id}. Partial update; only provided fields are updated.", "Response for GET list and GET one, POST and PUT.", "Response for GET list and POST." Every field: `Field(description="...")`; optional/defaults and `from_attributes` for responses — see § Schemas (Pydantic).
- **Models:** One `#` above each class and each enum. Style: "User account; auth via password_hash and session_epoch for token invalidation.", "Investment category (CEDEARs, FCI, dollars, …).", "Point-in-time value of an investment (one per investment per date)." Every field: `Field(...)` with PK/FK/description/max_length/default_factory as needed — see § Models (SQLModel).
- **Domain:** One `#` above class when the role isn’t obvious (value objects, enums, errors).

One or two lines per comment. No docstrings in the function body.
