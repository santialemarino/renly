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

- Never `git add .` or `git add -A`; stage files individually by name.
- Never stage `.claude/plans/`.
- Never stage `docs/internal/`.
- Never stage temporary markdown files unless the user explicitly names them.
- Pre-commit runs lint-staged plus `check:api`, `check:web`, and `test:api`; do not commit code that would fail those checks.

## PR asset upload policy

OFF by default. The agent verifies every UI change with `playwright-cli` per the `e2e-testing` skill — capturing screenshots/videos locally as part of that verification is fine — but the Screenshots & Recordings section is omitted from the PR body unless I explicitly ask for assets on that PR. Per-PR opt-in only; no standing "upload always" mode. When I ask, follow the hosting paths in the `pr-format` skill.

## Architecture rules

- Use API skills for backend work: `api-layering` and `api-methods-entities`.
- Use web skills for frontend work: `web-structure` and `web-components-pages`.
- Services own API transaction boundaries; repositories do not commit.
- Avoid N+1 queries. Add batch repository methods when data is needed in loops.
- API comments above function/class definitions end with periods.
- Web code uses the project type scale; avoid raw typography classes when project tokens exist.

## Review guidelines

- Flag P0/P1 issues only unless the PR asks for a broader review.
- Treat financial miscalculation, balance/currency errors, auth/session regressions, data-loss bugs, broken DB schema updates, and transaction mistakes as high priority.
- Check backend layer boundaries, repository/service method order, schema/model conventions, and no commits from repositories.
- Check frontend routing, translations, typography tokens, component ordering, and shared UI reuse.
- If schema changes were made, verify `apps/api/database/01_create_tables.sql` still represents a clean rebuild from zero.
- If behavior, setup, or public API changed, verify the relevant README or docs were updated.
- Treat missing tests as high priority when calculations, persistence, auth, API contracts, or shared UI behavior changed.
