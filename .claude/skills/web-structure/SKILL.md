---
name: web-structure
description: Frontend app structure and where to create files (pages, components, lib, config). Use when adding routes, pages, or organizing code in apps/web.
---

# Web structure (Renly frontend)

## App Router layout

- **`app/(auth)/`** — Route group for unauthenticated routes: login, signup. Layout does not require session.
- **`app/(protected)/`** — Route group for authenticated routes: dashboard, settings, etc. Layout calls `getSession()` and redirects to `LOGIN_ROUTE` when there is no valid session.
- **`app/layout.tsx`** — Root layout. Route groups each have their own `layout.tsx` for shared wrapper (e.g. auth layout, protected layout with session check).

## Where to create files

- **New page (route):** Add a folder under `app/(auth)/` or `app/(protected)/` with `page.tsx`. Add the path to `config/routes.ts` (e.g. `ROUTES.settings`) and use that constant for links and redirects — do not hardcode URLs.
- **Page-specific components:** In `_components/` next to the page, e.g. `app/(auth)/login/_components/login-card.tsx`. Only that page (and its children) should import these.
- **Shared across all protected pages:** In `app/(protected)/_components/`, e.g. `page-header.tsx`. For components used by more than one protected route but not outside it.
- **Shared logic (auth, API, utils):** `lib/` — e.g. `lib/auth.ts`, `lib/auth-api.ts`, `lib/utils/page.tsx`. Use for anything used by more than one route or shared between server and client.
- **Server-side data fetching (reads):** `lib/api/<feature>.ts` with `import 'server-only'`. Used directly in server components (`page.tsx`). Can be imported by multiple pages.
- **Server mutations:** `actions.ts` colocated with the page (`'use server'`). Called from client components. Feature-specific; do not put in `lib/`.
- **Used on multiple pages (this app only):** Put in the app's `components/` folder.
- **Reusable across apps (design system):** Put in `packages/ui/src/components`, add to the package's `index.ts`, and import from `@repo/ui/components` in the web app.
- **Routes and constants:** `config/routes.ts` for `ROUTES`, `AUTH_ROUTES`, `LOGIN_ROUTE`. Form validation constants (e.g. max length) can live in `lib/constants/`.

## Directory layout (apps/web/)

```
app/
├── layout.tsx
├── page.tsx
├── (auth)/                  # No session required
│   ├── layout.tsx
│   ├── login/
│   │   ├── page.tsx
│   │   └── _components/
│   └── signup/
│       ├── page.tsx
│       └── _components/
├── (protected)/             # getSession + redirect if missing
│   ├── layout.tsx
│   ├── _components/         # shared across all protected pages (e.g. page-header.tsx)
│   └── <route>/
│       └── page.tsx (+ _components/, actions.ts, schema.ts, etc.)
lib/                         # Auth, API, shared utils
config/
└── routes.ts                # ROUTES, AUTH_ROUTES, LOGIN_ROUTE
translations/                # en.json, es.json
packages/ui                  # Workspace — shared React components
```
