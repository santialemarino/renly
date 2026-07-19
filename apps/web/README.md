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

## Unit tests (Vitest)

Tests live in `tests/unit/`, split into two Vitest projects by file extension (`vitest.config.ts`): a `node` project for `*.test.ts` (pure functions — the locale/formatting layer + EN/ES keyset parity) and a `jsdom` project for `*.test.tsx` (React components driven with React Testing Library, e.g. `LocaleAmountInput`). The `@/*` alias is wired via `vite-tsconfig-paths`; the jsdom project loads `tests/setup-jsdom.ts`. Scripts:

- `pnpm test` — watch mode
- `pnpm test:run` — single run (what root `pnpm test:web` calls)

From repo root: `pnpm test:web`. Runs on every commit (pre-commit) and in CI Web. See the `testing` skill for what belongs here vs E2E.

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
- **`app/` brand assets** — Next file-convention metadata: `icon.svg` + `favicon.ico` + `apple-icon.png` (the R-monogram favicons), `manifest.ts` (PWA manifest), and `opengraph-image.tsx` (the social share card, drawn with `next/og` and the bundled Plus Jakarta Sans subset in `app/_og-fonts/`). Next auto-wires these into `<head>`; the root `layout.tsx` sets `metadataBase` (from `NEXT_PUBLIC_SITE_URL`), Open Graph/Twitter tags, and the `theme-color`.
- **`lib/`** — Auth, API client helpers, shared utils (e.g. `lib/auth.ts`, `lib/auth-api.ts`, `lib/utils/page.tsx` for metadata).
- **`config/`** — `routes.ts` for `ROUTES`, `AUTH_ROUTES`, `LOGIN_ROUTE`; use these instead of hardcoding paths.
- **`packages/ui`** — Shared React components (workspace dependency). Use for design system / reusable UI.
