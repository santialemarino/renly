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

## Structure

Request flow: **router → service → repository → DB**. Routers are HTTP-only; services hold business logic; repositories do data access. Schemas for request/response; `deps/` for FastAPI dependencies.

## Env

`.env` with: `DATABASE_URL`, `JWT_SECRET` (match Next.js `NEXTAUTH_SECRET`), `JWT_ALGORITHM=HS256`, `JWT_EXPIRE_MINUTES=10080`. Copy from `.env.example`.
