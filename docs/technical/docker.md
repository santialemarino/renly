# Docker Setup

Docker Compose configuration and Dockerfiles for running Renly services.

## Services

### postgres

| Property      | Value                                                 |
| ------------- | ----------------------------------------------------- |
| **Image**     | `postgres:16-alpine`                                  |
| **Container** | `renly-postgres`                                      |
| **Port**      | `5432:5432`                                           |
| **Volume**    | `postgres_data:/var/lib/postgresql/data` (persistent) |
| **Restart**   | `unless-stopped`                                      |

Environment variables with defaults: `POSTGRES_USER=renly`, `POSTGRES_PASSWORD=renly`, `POSTGRES_DB=renly`.

### api

| Property       | Value                   |
| -------------- | ----------------------- |
| **Dockerfile** | `docker/api.Dockerfile` |
| **Container**  | `renly-api`             |
| **Port**       | `8000:8000`             |
| **Depends on** | `postgres`              |
| **Restart**    | `unless-stopped`        |

Reads env from `.env` file at repo root. Also passes `DATABASE_URL`, `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES` explicitly via `environment`.

### web

| Property       | Value                   |
| -------------- | ----------------------- |
| **Dockerfile** | `docker/web.Dockerfile` |
| **Container**  | `renly-web`             |
| **Port**       | `3000:3000`             |
| **Restart**    | `unless-stopped`        |

`NEXT_PUBLIC_API_URL` is passed as a **build arg** (baked into the Next.js build at compile time, default `http://localhost:8000`). Runtime environment: `NODE_ENV=production`, `PORT=3000`.

## Network

All services share a custom bridge network named `renly-network` (defined in `docker-compose.yml` under `networks.default`).

## Dockerfiles

### API (`docker/api.Dockerfile`)

Two-stage build:

1. **builder** — `python:3.13-slim`. Installs `uv` from the official image, copies `pyproject.toml`, runs `uv sync --no-dev --no-editable` to create the venv, then copies the app code.
2. **runner** — `python:3.13-slim`. Copies the `.venv` and `app/` from builder. Installs `ca-certificates`. Runs `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

### Web (`docker/web.Dockerfile`)

Three-stage build:

1. **base** — `node:22-alpine`. Enables corepack (pnpm), sets `NEXT_TELEMETRY_DISABLED=1`.
2. **deps** — Copies workspace manifests (`pnpm-workspace.yaml`, `pnpm-lock.yaml`, and all `package.json` files), runs `pnpm install --frozen-lockfile`.
3. **builder** — Copies source code and node_modules from deps. Builds `@repo/ui` first, then the `web` app. `NEXT_PUBLIC_API_URL` is injected as a build arg.
4. **runner** — `node:22-alpine`. Copies `.next`, `public`, `package.json`, `next.config.js`, `node_modules`, and the UI package. Runs `pnpm start`.

## Running the full stack

```bash
# From repo root — starts postgres, api, and web
docker compose up --build

# Detached mode
docker compose up --build -d

# Stop everything
docker compose down

# Stop and remove volumes (deletes DB data)
docker compose down -v
```

The API applies no migrations on startup — the schema must already exist. For a fresh DB, apply the schema after Postgres is ready:

```bash
docker compose up -d postgres
docker exec -i renly-postgres psql -U renly -d renly < apps/api/database/01_create_tables.sql
docker compose up --build
```

Or use `pnpm db:init` which handles both starting Postgres and applying the schema.

## Running just Postgres (local dev)

For developing the API and web app outside Docker while using Docker only for the database:

```bash
# Start only the Postgres service
docker compose up -d postgres
```

Then set `DATABASE_URL=postgresql+asyncpg://renly:renly@localhost:5432/renly` in `apps/api/.env` and run the apps with `pnpm dev`.

To apply the schema on a fresh database:

```bash
docker exec -i renly-postgres psql -U renly -d renly < apps/api/database/01_create_tables.sql
```

Or simply run `pnpm db:init` which does both steps.
