# Renly API

FastAPI backend for Renly.

## Install

```bash
cd apps/api && uv sync
# or: pip install -r requirements.txt (with venv active)
```

## Run

From repo root: `pnpm dev:api`  
From here: `uv run uvicorn app.main:app --reload --port 8000`

Interactive API docs (Swagger UI): http://localhost:8000/docs

**Local DB:** From repo root, `pnpm db:init` starts Postgres and applies the schema.

## Env

`.env` with: `DATABASE_URL`, `JWT_SECRET` (same as Next.js `NEXTAUTH_SECRET`), `JWT_ALGORITHM=HS256`, `JWT_EXPIRE_MINUTES=10080`. See `.env.example`.
