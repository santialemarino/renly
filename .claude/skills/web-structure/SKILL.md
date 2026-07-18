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
- **Client hooks:** `lib/hooks/<name>.ts` — reusable `'use client'` hooks used by 2+ components (e.g. `use-search-params-navigation.ts`, `use-table-sort.ts`, `use-entity-form-dialog.ts`). One hook per file, kebab-case file named after the hook.
- **Server-side data fetching (reads):** `lib/api/<feature>.ts` with `import 'server-only'`. Used directly in server components (`page.tsx`). Can be imported by multiple pages.
- **Cross-entity API contract types:** `lib/api/types.ts` (e.g. `SortOrder`) — shared by multiple `lib/api/<feature>.ts` modules; entity-specific types stay in their feature module.
- **Server mutations:** `actions.ts` colocated with the page (`'use server'`). Called from client components. Feature-specific; do not put in `lib/`.
- **Used on multiple pages (this app only):** Put in the app's `components/` folder.
- **Reusable across apps (design system):** Put in `packages/ui/src/components`, add to the package's `index.ts`, and import from `@repo/ui/components` in the web app.
- **Routes:** `config/routes.ts` for `ROUTES`, `AUTH_ROUTES`, `LOGIN_ROUTE`.
- **Constants:** `lib/constants/<topic>.ts` — one file per topic (e.g. `animations.ts`, `currency.ts`, `charts.ts`). Only for constants imported by 2+ files. Single-file constants stay in the file that uses them.
- **i18n / locale:** `lib/i18n/` is the home for all locale + formatting code. `lib/i18n/locales.ts` holds the single `LOCALES` registry — the source of truth every locale-derived value flows from (`Locale`/`TextDirection` types, `DEFAULT_LOCALE`, `SUPPORTED_LOCALES`, `getLocaleTag`, `getDateFnsLocale`, `getLocaleDirection`, `LANGUAGE_OPTIONS`, `LANGUAGE_MODE_*`, `LOCALE_COOKIE`, browser-language detection). The pure formatters live alongside it (`format.ts`, `currency.ts`, `numeric-input.ts` — the last also carries the amount-input separator helpers), and the locale-bound hook is `create-formatters.ts` (pure factory) + `formatters.ts` (`useFormatters()`, client) + `formatters-server.ts` (`getFormatters()`, `server-only`). Components format via the hook — see web-components-pages "Formatting & locale". Adding a language is one registry entry plus a matching `translations/<code>.json`. The next-intl framework config stays at its required root path `i18n/request.ts` (not under `lib/`).

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
