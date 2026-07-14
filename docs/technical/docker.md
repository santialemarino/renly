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

| Property       | Value                                                 |
| -------------- | ----------------------------------------------------- |
| **Dockerfile** | `docker/api.Dockerfile`                               |
| **Container**  | `renly-api`                                           |
| **Ports**      | `8000:8000` (API) and `3000:3000` (web — see Network) |
| **Depends on** | `postgres`                                            |
| **Restart**    | `unless-stopped`                                      |

Reads an **optional** root `.env` (`env_file` long syntax, `required: false`) — the stack boots
zero-config without it. `environment` provides working local defaults with **service-name hosts**:
`DATABASE_URL` and `DATABASE_ADMIN_URL` default to `postgresql+asyncpg://renly:renly@postgres:5432/renly`,
plus a dev placeholder `JWT_SECRET` and `WEB_BASE_URL`. Every other API var comes from the root
`.env` (if present) or its in-code default (`config.py`). Local compose runs **single-role** (the
owner for both DB URLs), so Row-Level Security is bypassed here as in any single-role local setup;
production uses the two-role env contract from the deploy runbook instead of compose. Any root
`.env` override of the DB URLs must use the `postgres` service host.

### web

| Property         | Value                                                         |
| ---------------- | ------------------------------------------------------------- |
| **Dockerfile**   | `docker/web.Dockerfile`                                       |
| **Container**    | `renly-web`                                                   |
| **Network mode** | `service:api` (shares the api namespace — no port of its own) |
| **Restart**      | `unless-stopped`                                              |

Build args (both baked into the Next.js build at compile time): `NEXT_PUBLIC_API_URL` (default
`http://localhost:8000`) and `NEXT_PUBLIC_SENTRY_DSN` (default empty → Sentry off). Runtime
environment: `NODE_ENV=production`, `PORT=3000`, `NEXTAUTH_URL` (default `http://localhost:3000`),
and `NEXTAUTH_SECRET` (must equal the api's `JWT_SECRET`; shares the same placeholder default). The
web service uses `network_mode: service:api` so the single build-time-inlined `NEXT_PUBLIC_API_URL`
(`http://localhost:8000`) resolves from **both** sides: the host browser reaches the API via the
published port, and the web server's own SSR fetches reach it on localhost inside the shared
namespace. A service-name URL would fix SSR but break the browser-side auth forms, and `NEXT_PUBLIC_*`
values cannot be changed at runtime — hence one URL that works everywhere.

## Network

The `postgres` and `api` services sit on a custom bridge network named `renly-network` (defined in
`docker-compose.yml` under `networks.default`). The `web` service has no address of its own — it
shares the api service's network namespace (`network_mode: service:api`), so ports `8000` (API) and
`3000` (web) are both published on the api service.

## Dockerfiles

### API (`docker/api.Dockerfile`)

Two-stage build:

1. **builder** — `python:3.13-slim`. Installs `uv` from the official image, copies `pyproject.toml`, runs `uv sync --no-dev --no-editable` to create the venv, then copies the app code.
2. **runner** — `python:3.13-slim`. Copies the `.venv` and `app/` from builder. Installs `ca-certificates`. Runs `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

### Web (`docker/web.Dockerfile`)

Three-stage build:

1. **base** — `node:22-alpine`. Enables corepack (pnpm), sets `NEXT_TELEMETRY_DISABLED=1`.
2. **deps** — Copies workspace manifests (`pnpm-workspace.yaml`, `pnpm-lock.yaml`, and all `package.json` files), runs `pnpm install --frozen-lockfile`.
3. **builder** — Copies source code and node_modules from deps. Builds `@repo/ui` first, then the `web` app. Both `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_SENTRY_DSN` are injected as build args (inlined into the client bundle).
4. **runner** — `node:22-alpine`. Copies `.next`, `public`, `package.json`, `next.config.js`, `node_modules`, and the UI package. Re-declares both `NEXT_PUBLIC_*` build args (ARGs reset per stage). Runs `node_modules/.bin/next start`.

## Running the full stack

**Requirements:** Docker Compose ≥ 2.24 (the api service uses the long-form `env_file` syntax).

The stack boots zero-config — the root `.env` is optional (override-only) and every required var
has a working local default. A fresh database, however, needs its schema applied first, because the
API applies no migrations on startup:

```bash
# From repo root — apply the schema to a fresh DB (starts renly-postgres and runs 01_create_tables.sql)
pnpm db:init

# Then start postgres, api, and web
docker compose up --build

# Detached mode
docker compose up --build -d

# Stop everything
docker compose down

# Stop and remove volumes (deletes DB data)
docker compose down -v
```

If you prefer not to use `pnpm db:init`, apply the schema manually after Postgres is ready:

```bash
docker compose up -d postgres
docker exec -i renly-postgres psql -U renly -d renly < apps/api/database/01_create_tables.sql
docker compose up --build
```

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
