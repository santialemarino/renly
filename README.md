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

| Command           | Description                                                                                                                       |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `pnpm db:init`    | Start Postgres and apply schema (first time)                                                                                      |
| `pnpm db:fork`    | Fork DB from `DATABASE_URL` into a local container (see [docs/technical/local-db-forking.md](docs/technical/local-db-forking.md)) |
| `pnpm db:migrate` | Apply pending Alembic migrations to the DB (`alembic upgrade head`)                                                               |

**Lint & format**

| Command                      | Description                                                                              |
| ---------------------------- | ---------------------------------------------------------------------------------------- |
| `pnpm lint`                  | ESLint — report errors                                                                   |
| `pnpm lint:fix`              | ESLint — auto-fix                                                                        |
| `pnpm format`                | Format everything (web + api)                                                            |
| `pnpm format:check`          | Check formatting — fails if unformatted (CI)                                             |
| `pnpm format:api`            | Ruff format on `apps/api`                                                                |
| `pnpm format:check:api`      | Ruff format check on `apps/api` (CI)                                                     |
| `pnpm format:web`            | Prettier write — JS/TS/CSS/JSON/MD                                                       |
| `pnpm format:check:web`      | Prettier check (CI)                                                                      |
| `pnpm check:api`             | API app import check                                                                     |
| `pnpm check:web`             | Web TypeScript type check                                                                |
| `pnpm check-types`           | TypeScript type check (all workspaces/turbo)                                             |
| `pnpm test:api`              | Run API unit tests (pytest)                                                              |
| `pnpm --filter web test:e2e` | Run Playwright E2E tests (web) — needs `pnpm dev` and `playwright install chromium` once |

## Documentation

- **[Solution overview](docs/public/solution.md)** — What Renly is and who it's for
- **[API reference](docs/public/api-reference.md)** — All endpoints, params, and error codes
- **[Investment categories](docs/public/investment-categories.md)** — Categories, capabilities, and price sources
- **[Metrics](docs/public/metrics.md)** — Financial metric formulas (TWR, IRR, period return)
- **[Data model](docs/public/data-model.md)** — Tables, relationships, and design rationale

Technical docs for developers: [`docs/technical/`](docs/technical/) (auth flow, scheduler, env vars, currency handling, providers, Docker).

## Code quality

On every `git commit`, Husky runs:

- **lint-staged** — Prettier on staged JS/TS/CSS/JSON/MD (with import sort via `@ianvs/prettier-plugin-sort-imports`); ESLint fix on staged TS/TSX in `apps/web` and `packages/ui`. Formatted files are re-staged.
- **API** — `pnpm check:api` so the app loads (runs from `apps/api`).
- **API tests** — `pnpm test:api` runs pytest unit tests.
- **Web** — `pnpm check:web` so TypeScript compiles.

To run manually: `pnpm format`, `pnpm lint:fix`, `pnpm check:api`, `pnpm check:web`.

## Docker

- **Postgres:** `pnpm db:init` starts Postgres 16 on port 5432 and applies the schema (first time). User/pass/db: `renly`. Set `DATABASE_URL=postgresql+asyncpg://renly:renly@localhost:5432/renly` in `apps/api/.env`.
- **Full stack in Docker:** Put required env vars in a root `.env` (see `apps/api/.env.example` and `apps/web/.env.example`), then `pnpm dev:docker` (or `docker compose up -d`). First time, run `pnpm db:init` after to apply the schema to the DB.
- **Build images (from repo root):**
  - API: `docker build -f docker/api.Dockerfile .`
  - Web: `docker build -f docker/web.Dockerfile --build-arg NEXT_PUBLIC_API_URL=https://api.example.com .`

## Conductor / worktrees

Configured for [Conductor](https://conductor.build) — or any `git worktree`-based parallel-agent workflow — via `conductor.json` and `.worktreeinclude`:

- **`scripts.setup`** runs `pnpm install` and warms the API venv (`uv sync`); **`scripts.run`** is `pnpm dev`.
- **`runScriptMode` is `nonconcurrent`**: only one workspace serves the app at a time, because all worktrees share the single `renly-postgres` container and the fixed dev ports (web 3000, api 8000). Agents in other worktrees still edit code and run `pnpm test:api` (which mocks the DB) with no contention. Running multiple live apps at once would need `$CONDUCTOR_PORT` wired into the dev scripts plus a per-worktree DB via `pnpm db:fork` — intentionally not set up.
- **`.worktreeinclude`** copies the gitignored files a fresh worktree needs: `apps/api/.env`, `apps/web/.env`, and `.claude/settings.json` (so the agent inherits the repo's permission allowlist instead of the global one).
