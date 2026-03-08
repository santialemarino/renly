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

## Structure

- **`app/`** — App Router: `(auth)/` (login, signup), `(protected)/` (dashboard, etc.). One `page.tsx` per route; route-specific components in `_components/` next to the page.
- **`lib/`** — Auth, API client helpers, shared utils (e.g. `lib/auth.ts`, `lib/auth-api.ts`, `lib/utils/page.tsx` for metadata).
- **`config/`** — `routes.ts` for `ROUTES`, `AUTH_ROUTES`, `LOGIN_ROUTE`; use these instead of hardcoding paths.
- **`packages/ui`** — Shared React components (workspace dependency). Use for design system / reusable UI.
