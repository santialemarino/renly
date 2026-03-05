# Renly

Personal financial management app: investment tracking MVP (monthly snapshots, dashboard, ARS/USD), extensible to income/expenses, subscriptions, and automation. Turborepo monorepo.

## Setup

```bash
pnpm install
pnpm build   # builds UI styles (required before first dev)
pnpm db:init # start Postgres and apply schema (first time only)
pnpm dev
```

**Requirements:** Node.js 22+, pnpm 10+, Python 3.13+, Docker (for local Postgres).

**First-time DB:** From repo root, run `pnpm db:init` to start the Postgres container (docker compose) and apply the schema. Set `DATABASE_URL=postgresql+asyncpg://renly:renly@localhost:5432/renly` in `apps/api/.env`.

## Structure

- `apps/web` — Next.js frontend (port 3000)
- `apps/api` — FastAPI backend (port 8000). See `apps/api/README.md` for Python setup.
- `packages/ui` — Shared React components

## Scripts

**Dev**

| Command           | Description                                                              |
| ----------------- | ------------------------------------------------------------------------ |
| `pnpm dev`        | Start all apps (web + api on host; run `pnpm db:init` for DB first time) |
| `pnpm dev:docker` | Start full stack in Docker (postgres + api + web)                        |
| `pnpm dev:web`    | Web only                                                                 |
| `pnpm dev:api`    | API only                                                                 |

**Build**

| Command          | Description |
| ---------------- | ----------- |
| `pnpm build`     | Build all   |
| `pnpm build:web` | Web only    |
| `pnpm build:api` | API only    |

**DB**

| Command        | Description                                                                                                   |
| -------------- | ------------------------------------------------------------------------------------------------------------- |
| `pnpm db:init` | Start Postgres and apply schema (first time)                                                                  |
| `pnpm db:fork` | Fork DB from `DATABASE_URL` into a local container (see [docs/local-db-forking.md](docs/local-db-forking.md)) |

**Lint & format**

| Command                 | Description                                  |
| ----------------------- | -------------------------------------------- |
| `pnpm lint`             | ESLint — report errors                       |
| `pnpm lint:fix`         | ESLint — auto-fix                            |
| `pnpm format`           | Format everything (web + api)                |
| `pnpm format:check`     | Check formatting — fails if unformatted (CI) |
| `pnpm format:web`       | Prettier write — JS/TS/CSS/JSON/MD           |
| `pnpm format:check:web` | Prettier check (CI)                          |
| `pnpm format:api`       | Ruff format on `apps/api`                    |
| `pnpm format:check:api` | Ruff format check on `apps/api` (CI)         |
| `pnpm check-types`      | TypeScript type check                        |

## Code quality

On every `git commit`, Husky runs lint-staged automatically:

- **Prettier** formats staged JS/TS/CSS/JSON/MD files and sorts imports via `@ianvs/prettier-plugin-sort-imports`.
- **ESLint** auto-fixes staged TS/TSX files in `apps/web` and `packages/ui`.
- Formatted files are re-staged before the commit is finalized, so the commit always contains clean code.

To run manually: `pnpm format` (format everything), `pnpm lint:fix` (ESLint fix).

## Docker

- **Postgres:** `pnpm db:init` starts Postgres 16 on port 5432 and applies the schema (first time). User/pass/db: `renly`. Set `DATABASE_URL=postgresql+asyncpg://renly:renly@localhost:5432/renly` in `apps/api/.env`.
- **Full stack in Docker:** Put required env vars in a root `.env` (see `apps/api/.env.example` and `apps/web/.env.example`), then `pnpm dev:docker` (or `docker compose up -d`). First time, run `pnpm db:init` after to apply the schema to the DB.
- **Build images (from repo root):**
  - API: `docker build -f docker/api.Dockerfile .`
  - Web: `docker build -f docker/web.Dockerfile --build-arg NEXT_PUBLIC_API_URL=https://api.example.com .`
