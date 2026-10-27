# Renly - Codex context

Renly is a personal finance app that unifies investments, cash/bank accounts, and credit-card debt into one net-worth picture, alongside income and expense tracking. It is a monorepo with `apps/web` for Next.js, `apps/api` for FastAPI, and `packages/ui` for shared UI.

## Start here

Read the `agent-workflow` skill first when doing substantive local work. Codex skills live under `.agents/skills/`; Claude skills remain under `.claude/skills/`.

## Key commands

```bash
pnpm dev
pnpm db:init
pnpm check:api
pnpm check:web
pnpm test:api
pnpm test:web
pnpm format
pnpm lint:fix
```

## Canonical docs

- API setup and structure: `apps/api/README.md`.
- Web setup: `apps/web/README.md`.
- DB schema: `apps/api/database/01_create_tables.sql`.
- Public docs: `docs/public/`.
- Technical docs: `docs/technical/`.
- Internal docs: `docs/internal/` are gitignored and must not be committed.

## Hard rules

- Never `git add .` or `git add -A` — stage files individually by name
- Never stage `.claude/plans/` or `docs/internal/` — both gitignored
- Never stage temporary or scratch `.md` files unless the user explicitly names them
- Pre-commit (`scripts/pre-commit.sh`) is scoped by the staged paths: lint-staged always, then `check:api` + `test:api` for staged API paths, `check:web` + `test:web` for staged web/`packages/` paths, everything for root config and scripts, nothing more for docs and skills — plus the other app's cross-app tests whenever code is staged (see `agent-workflow` §2). Don't commit code that would fail any of these

## PR asset upload policy

OFF by default. The agent verifies every UI change with `playwright-cli` per the `e2e-testing` skill — capturing screenshots/videos locally as part of that verification is fine — but the Screenshots & Recordings section is omitted from the PR body unless I explicitly ask for assets on that PR. Per-PR opt-in only; no standing "upload always" mode. When I ask, follow the hosting paths in the `pr-format` skill.

## Architecture and review rules

The architecture rules and the review standard (P0/P1 rubric) live in the `agent-workflow` skill (§1 and §7), so Claude and Codex follow the same ones.
