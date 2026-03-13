# Renly — Claude context

Renly is a personal investment tracker (2-3 users). Monorepo: `apps/web` (Next.js), `apps/api` (FastAPI), `packages/ui`. See `arch_en.md` for the full architecture and `README.md` for all dev commands.

## Start here

Always read the **agent-workflow** skill first. It tells you which other skills to load and covers checks, docs, and commit rules.

## Key commands (from repo root)

```bash
pnpm dev          # start web (3000) + api (8000); run db:init first if DB is fresh
pnpm db:init      # start Postgres and apply schema (first time only)
pnpm check:api    # API import check (same as pre-commit)
pnpm check:web    # TypeScript type check (same as pre-commit)
pnpm format       # format everything
pnpm lint:fix     # ESLint auto-fix
```

## Canonical docs

- **Architecture & product spec:** `arch_en.md` — read this before any new feature
- **API setup & structure:** `apps/api/README.md`
- **Web setup:** `apps/web/README.md` (if exists)
- **DB schema:** `apps/api/database/01_create_tables.sql`

## Hard rules

- Never `git add .` or `git add -A` — stage files individually by name
- Never stage `.claude/projects/` — gitignored for a reason
- Never stage temporary `.md` files unless the user explicitly names them
- Pre-commit runs lint-staged + `check:api` + `check:web` — don't commit code that would fail these
