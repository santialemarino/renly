# Renly

Personal financial management app: investment tracking MVP (monthly snapshots, dashboard, ARS/USD), extensible to income/expenses, subscriptions, and automation. Turborepo monorepo.

## Setup

```bash
pnpm install
pnpm build   # builds UI styles (required before first dev)
pnpm dev
```

**Requirements:** Node.js 22+, pnpm 10+, Python 3.13+

## Structure

- `apps/web` — Next.js frontend (port 3000)
- `apps/api` — FastAPI backend (port 8000). See `apps/api/README.md` for Python setup.
- `packages/ui` — Shared React components

## Scripts

| Command                 | Description                                             |
| ----------------------- | ------------------------------------------------------- |
| `pnpm dev`              | Start all apps                                          |
| `pnpm dev:web`          | Web only                                                |
| `pnpm dev:api`          | API only                                                |
| `pnpm build`            | Build all                                               |
| `pnpm lint`             | ESLint — report errors across all packages              |
| `pnpm lint:fix`         | ESLint — auto-fix violations across all packages        |
| `pnpm format`           | Format everything (web + api)                           |
| `pnpm format:check`     | Check formatting everywhere — fails if unformatted (CI) |
| `pnpm format:web`       | Prettier write — JS/TS/CSS/JSON/MD                      |
| `pnpm format:check:web` | Prettier check — JS/TS/CSS/JSON/MD (CI)                 |
| `pnpm format:api`       | Ruff format on `apps/api` Python files                  |
| `pnpm format:check:api` | Ruff format check on `apps/api` (CI)                    |
| `pnpm check-types`      | TypeScript type check across all packages               |

## Code quality

On every `git commit`, Husky runs lint-staged automatically:

- **Prettier** formats staged JS/TS/CSS/JSON/MD files and sorts imports via `@ianvs/prettier-plugin-sort-imports`.
- **ESLint** auto-fixes staged TS/TSX files in `apps/web` and `packages/ui`.
- Formatted files are re-staged before the commit is finalized, so the commit always contains clean code.

To run manually: `pnpm format` (format everything), `pnpm lint:fix` (ESLint fix).

## Docker

- **Postgres (local):** `docker compose up -d` — Postgres 16 on port 5432 (user/pass/db: `renly`). Use `DATABASE_URL=postgresql+asyncpg://renly:renly@localhost:5432/renly` in `apps/api/.env`.
- **Full stack (postgres + api + web):** Put required env vars in a root `.env` (see `apps/api/.env.example` and `apps/web/.env.example`), then `docker compose up -d`.
- **Build images (from repo root):**
  - API: `docker build -f docker/api.Dockerfile .`
  - Web: `docker build -f docker/web.Dockerfile --build-arg NEXT_PUBLIC_API_URL=https://api.example.com .`
