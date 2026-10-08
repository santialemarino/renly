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

From repo root: `pnpm test:web`. Runs on every commit that stages web code (pre-commit) and in CI Web; files named `*.cross-app.test.ts` read the API's source and run on every code commit (`pnpm --filter web run test:cross-app`). See the `testing` skill for what belongs here vs E2E.

## E2E tests (Playwright)

Tests live in `tests/e2e/`. Config in `playwright.config.ts`. Scripts:

- `pnpm test:e2e` — headless, single browser
- `pnpm test:e2e:ui` — Playwright UI mode
- `pnpm test:e2e:headed` — visible browser
- `pnpm test:e2e:debug` — Playwright Inspector
- `pnpm test:e2e:report` — open last HTML report

First-time setup (one-off per machine): `pnpm exec playwright install chromium`.

Prerequisite for every run: `pnpm dev` running on http://localhost:3000 (override with `PLAYWRIGHT_BASE_URL=...`).

In CI, `.github/workflows/ci.web-e2e.yml` runs the whole suite against a production build and a seeded throwaway account — on a PR that touches the e2e floor (schema, migrations, dependency manifests, the harness) or carries the `run-e2e` label, every night on `main`, and on demand. The HTML report and server logs are uploaded on every run; traces, screenshots and videos only for failed tests.

For full conventions (selectors, auth, fixtures, `playwright-cli` workflow), see the `e2e-testing` skill in `.claude/skills/e2e-testing/SKILL.md`.

## Structure

- **`app/`** — App Router: `(auth)/` (login, signup), `(protected)/` (dashboard, etc.). One `page.tsx` per route; route-specific components in `_components/` next to the page. Every protected route also has a `loading.tsx` rendering the shared `PageSkeleton` (a unit test derives the route list and fails on a missing one), and a failed read lands in an error boundary drawn inside its own surface — each route group has an `error.tsx`, `app/error.tsx` catches the group layouts and `app/global-error.tsx` the root layout — all translated, with a retry that re-fetches the server data. Each protected page's `lib/api` reads are classified (a unit test fails on an unclassified bare read); the error boundaries' copy lives in `translations/error-boundary/`.
- **`app/` brand assets** — Next file-convention metadata: `icon.svg` + `favicon.ico` + `apple-icon.png` (the R-monogram favicons), `manifest.ts` (PWA manifest), and `opengraph-image.tsx` (the social share card, drawn with `next/og` and the bundled Plus Jakarta Sans subset in `app/_og-fonts/`). Next auto-wires these into `<head>`; the root `layout.tsx` sets `metadataBase` (from `NEXTAUTH_URL`), Open Graph/Twitter tags, and the `theme-color`.
- **`lib/`** — Auth, API client helpers, shared utils (e.g. `lib/auth.ts`, `lib/auth-api.ts`, `lib/utils/page.tsx` for metadata).
- **`config/`** — `routes.ts` for `ROUTES`, `AUTH_ROUTES`, `LOGIN_ROUTE`; use these instead of hardcoding paths.
- **`public/sw.js`** — The service worker, which exists only so the browser can receive web push. It deliberately caches nothing: an offline strategy for a finance app is a way to show somebody a stale balance, and a caching worker that ships once is then permanently in the way of every deploy. `lib/push.ts` is the browser half (register, permission, subscribe) and `/notifications` is where it is turned on and off, per browser.
- **`packages/ui`** — Shared React components (workspace dependency). Use for design system / reusable UI. It has no i18n layer of its own, so the handful of accessible names it renders itself (a dialog's close ✕, a search field's clear button, the pagination arrows, the mobile sidebar) come from `UiLabelsProvider`, which the root `layout.tsx` mounts once with values from `common.ui`. Adding a string the package renders itself means adding it to `DEFAULT_UI_LABELS`, both translation files and that provider call — a unit test fails if the four disagree.
