# Renly API

FastAPI backend for Renly.

## Install

```bash
cd apps/api && uv sync
```

(Or with venv: `pip install -r requirements.txt`.)

## Run

From repo root: `pnpm dev:api`  
From here: `uv run uvicorn app.main:app --reload --port 8000`

Docs (Swagger): http://localhost:8000/docs

**Local DB:** From repo root, `pnpm db:init` starts Postgres and applies the schema.

## Check (no server)

From repo root: `pnpm check:api` — same as pre-commit/CI; catches import and model errors. (Runs `uv run python -c "from app.main import app"` in `apps/api`.)

## Migrations

Schema is managed two ways that stay in sync:

- `apps/api/database/01_create_tables.sql` — the canonical full schema. `pnpm db:init` builds a fresh DB from it and stamps Alembic to head.
- Alembic migrations (`apps/api/migrations/versions/`) — incremental changes for existing databases. `pnpm db:migrate` (`alembic upgrade head`) brings a live DB up to date.

When you change the schema, update **both**: edit `01_create_tables.sql` and add a migration — `pnpm --filter api run migrate:make "describe the change"` (autogenerates against the models), review the generated file under `migrations/versions/`, then `pnpm db:migrate`.

## Structure

Request flow: **router → service → repository → DB**. Routers are HTTP-only; services hold business logic; repositories do data access. Schemas for request/response; `deps/` for FastAPI dependencies.

## Test

From repo root: `pnpm test:api`
From here: `uv run pytest tests/ -v`

## Env

`.env` with: `DATABASE_URL`, `JWT_SECRET` (match Next.js `NEXTAUTH_SECRET`), `JWT_ALGORITHM=HS256`, `JWT_EXPIRE_MINUTES=10080`, `ENVIRONMENT` (`development`/`production` — `production` disables docs and debug), `CORS_ORIGINS` (comma-separated allowed origins), `TRUSTED_PROXY_COUNT` (reverse-proxy hop count for client-IP rate limiting; `0` when reached directly). Copy from `.env.example`. External API URLs (DolarApi, Frankfurter, CoinGecko, Comafi) are constants in the service layer.
