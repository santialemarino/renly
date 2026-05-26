# Renly Web

Next.js 16 (App Router) frontend for Renly.

## Install

From repo root: `pnpm install` (web is part of the monorepo). Then `pnpm build` once to build UI styles if needed.

## Run

From repo root: `pnpm dev:web`  
From here: `pnpm dev`

http://localhost:3000

## Check (no server)

From repo root: `pnpm check:web` — Next typegen + `tsc --noEmit`. Same as pre-commit/CI.

## E2E tests (Playwright)

Tests live in `tests/e2e/`. Config in `playwright.config.ts`. Scripts:

- `pnpm test:e2e` — headless, single browser
- `pnpm test:e2e:ui` — Playwright UI mode
- `pnpm test:e2e:headed` — visible browser
- `pnpm test:e2e:debug` — Playwright Inspector
- `pnpm test:e2e:report` — open last HTML report

First-time setup (one-off per machine): `pnpm exec playwright install chromium`.

Prerequisite for every run: `pnpm dev` running on http://localhost:3000 (override with `PLAYWRIGHT_BASE_URL=...`).

For full conventions (selectors, auth, fixtures, `playwright-cli` workflow), see the `e2e-testing` skill in `.claude/skills/e2e-testing/SKILL.md`.

## Structure

- **`app/`** — App Router: `(auth)/` (login, signup), `(protected)/` (dashboard, etc.). One `page.tsx` per route; route-specific components in `_components/` next to the page.
- **`lib/`** — Auth, API client helpers, shared utils (e.g. `lib/auth.ts`, `lib/auth-api.ts`, `lib/utils/page.tsx` for metadata).
- **`config/`** — `routes.ts` for `ROUTES`, `AUTH_ROUTES`, `LOGIN_ROUTE`; use these instead of hardcoding paths.
- **`packages/ui`** — Shared React components (workspace dependency). Use for design system / reusable UI.
