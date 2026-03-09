---
name: api-layering
description: Backend API structure and where to create files (routers, services, repositories, schemas, domain, utils, helpers). Use when adding endpoints, new features, or organizing code in apps/api.
---

# API layering (Renly backend)

## Flow and layers

Request flow: **router → service → repository → DB**.

- **routers/** — HTTP only: validate body, call service, return response or raise HTTPException. Use **schemas** for request/response.
- **services/** — Business logic: orchestrate use cases, call repositories. Use **domain** types and **models**; no HTTP or raw SQL.
- **repositories/** — Data access: run queries, add/commit. Use **models** and session only.
- **schemas/** — Pydantic request/response DTOs (HTTP contract).
- **domain/** — Types used by services only (value objects, enums, errors). Not HTTP, not DB.
- **models/** — SQLModel tables (DB entities).
- **deps/** — FastAPI dependencies (e.g. SessionDep, CurrentUser). Injected by the framework.

## Where to create files

- **New feature (e.g. investments):** add one file per layer: `routers/investments.py`, `services/investment_service.py`, `repositories/investment_repository.py`, `schemas/investment.py`, and optionally `domain/investment.py`.
- **New endpoint in existing feature:** add the route in the existing router; add service/repository functions in the existing service/repository files. Split into a new file only when a file gets too large or the domain is clearly separate.

## Utils vs helpers

- **utils** — General-purpose, not tied to one entity or service. Used across multiple services or the app.
  - **Where:** `app/utils/` (e.g. `app/utils/datetime.py`, `app/utils/validation.py`). If only used by one layer, `app/<layer>/utils.py` or `app/<layer>/utils/<name>.py` (e.g. `app/services/utils.py` for service-wide utils).
- **helpers** — Tied to a specific service or entity (e.g. auth, user, investment).
  - **Where:** next to the code that uses it: `app/services/auth_helpers.py` (used only by auth_service), or `app/repositories/user_repository_helpers.py` if needed. Prefer a single file per feature (e.g. `auth_helpers.py`) rather than a generic "helpers" folder.

Rule: if it’s used by one service/entity only → **helper** file next to that feature. If it’s generic and reusable across features → **utils** (under `app/utils/` or under the layer if layer-scoped).

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

Do not put business logic in routers or SQL in services. Do not put HTTP types (request/response bodies) in domain or models.
