---
name: web-structure
description: Frontend app structure and where to create files (pages, components, lib, config). Use when adding routes, pages, or organizing code in apps/web.
---

# Web structure (Renly frontend)

## App Router layout

- **`app/(auth)/`** — Route group for unauthenticated routes: login, signup. Layout does not require session.
- **`app/(protected)/`** — Route group for authenticated routes: dashboard, settings, etc. Layout calls `getSession()` and redirects to `LOGIN_ROUTE` when there is no valid session.
- **`app/layout.tsx`** — Root layout. Route groups each have their own `layout.tsx` for shared wrapper (e.g. auth layout, protected layout with session check).
- **Error boundaries — one per surface, plus two fallbacks, and a failed read is meant to reach one.** Each route group has its own `error.tsx`, rendered INSIDE that group's layout so the visitor keeps the chrome they were using: `(protected)/error.tsx` keeps the sidebar and mobile bar, `(public)/error.tsx` the site header and footer, `(auth)/error.tsx` the auth column (with a home link, since it has no nav). `app/error.tsx` catches the group LAYOUTS themselves (a segment's `error.tsx` sits inside its layout, so a protected-layout failure lands there). `app/global-error.tsx` replaces the root layout when that throws: it resolves the locale itself (`resolveLocale` in `lib/i18n/locales.ts`, the same rule `i18n/request.ts` uses) and renders copy it imports STATICALLY, so it can never render empty — which is why `common.errorBoundary` lives in its own small `translations/error-boundary/<code>.json` (exported as `ERROR_BOUNDARY_MESSAGES` from `lib/i18n/error-boundary-messages.ts`, and merged into `common` by `i18n/request.ts` for every other render) rather than in the main files, which are too large to ship to every page. All of them render `ErrorState` (`components/error-state.tsx`), whose retry is `router.refresh()` + `reset()` in one transition (`reset()` alone re-renders the failed payload), and report through `useReportBoundaryError` (a caught error never reaches the browser SDK's global handler; one with a `digest` was already reported on the server). `tests/unit/error-boundary-coverage.test.ts` derives the route groups and fails on one without its boundary.
- **Loading states — every protected `page.tsx` has a `loading.tsx` in its OWN directory**, rendering `PageSkeleton` (`app/(protected)/_components/page-skeleton.tsx`) and nothing else. Own directory, not an ancestor's: Next shows the NEAREST boundary, so a parent's `loading.tsx` paints the parent page's header over the child. Pass `namespace` when the page's header is `t('title')` / `t('subtitle')` from that namespace, and omit it when the title is data (an account's name, a pot's label); pick `body` (`table` / `dashboard` / `form` / `sections`) plus `backLink` / `loose` to match the page's frame, so the swap moves nothing. A list page passes `toolbar` as its `EntityListToolbar`'s controls in order — `filters` and `actions`, each `{ kind, label }` with a translation KEY — and the skeleton lays them out with the toolbar's own classes (`components/entity-list-toolbar-layout.ts`, which `EntityListToolbar` renders from too) and sizes each by its real text, so the placeholder row wraps exactly where the real one does in either language; a dashboard with the period picker passes `periodPicker`. Controls only some accounts see (the scope pill, the collections filter) and dismissible hints stay out: a loading state cannot know them. `tests/e2e/loading-layout.auth.spec.ts` holds each list toolbar and dashboard picker to within 2px of its placeholder at 390 and 1280, in both locales, against a production build (it skips itself on a dev server, which prefetches no loading state). `tests/unit/route-loading-coverage.test.ts` derives the route list from the filesystem and enforces all of this.

## Where to create files

- **New page (route):** Add a folder under `app/(auth)/` or `app/(protected)/` with `page.tsx`. Add the path to `config/routes.ts` (e.g. `ROUTES.settings`) and use that constant for links and redirects — do not hardcode URLs.
- **Page-specific components:** In `_components/` next to the page, e.g. `app/(auth)/login/_components/login-card.tsx`. Only that page (and its children) should import these.
- **Shared across all protected pages:** In `app/(protected)/_components/`, e.g. `page-header.tsx`. For components used by more than one protected route but not outside it.
- **Shared logic (auth, API, utils):** `lib/` — e.g. `lib/auth.ts`, `lib/auth-api.ts`, `lib/utils/page-metadata.tsx`. Use for anything used by more than one route or shared between server and client.
- **Client hooks:** `lib/hooks/<name>.ts` — reusable `'use client'` hooks used by 2+ components (e.g. `use-search-params-navigation.ts`, `use-table-sort.ts`, `use-entity-form-dialog.ts`, `use-deferred-dialog-swap.ts`). One hook per file, kebab-case file named after the hook.
- **Server-side data fetching (reads):** `lib/api/<feature>.ts` with `import 'server-only'`. Used directly in server components (`page.tsx`). Can be imported by multiple pages.
- **Cross-entity API contract types:** `lib/api/types.ts` (e.g. `SortOrder`) — shared by multiple `lib/api/<feature>.ts` modules; entity-specific types stay in their feature module.
- **Server mutations:** `actions.ts` colocated with the page (`'use server'`). Called from client components. Feature-specific; do not put in `lib/`.
- **Used on multiple pages (this app only):** Put in the app's `components/` folder.
- **Reusable across apps (design system):** Put in `packages/ui/src/components`, add to the package's `index.ts`, and import from `@repo/ui/components` in the web app.
- **Routes:** `config/routes.ts` for `ROUTES`, `AUTH_ROUTES`, `LOGIN_ROUTE`, `PUBLIC_ROUTES`/`PROTECTED_ROUTES`, and the help-page anchors any in-app deep link must come from (`HELP_ANCHORS` + `helpAnchorPath`).
- **Constants:** `lib/constants/<topic>.ts` — one file per topic (e.g. `animations.ts`, `currency.ts`, `charts.ts`). Only for constants imported by 2+ files. Single-file constants stay in the file that uses them.
- **i18n / locale:** `lib/i18n/` is the home for all locale + formatting code. `lib/i18n/locales.ts` holds the single `LOCALES` registry — the source of truth every locale-derived value flows from (`Locale`/`TextDirection` types, `DEFAULT_LOCALE`, `SUPPORTED_LOCALES`, `getLocaleTag`, `getDateFnsLocale`, `getLocaleDirection`, `LANGUAGE_OPTIONS`, `LANGUAGE_MODE_*`, `LOCALE_COOKIE`, browser-language detection). The pure formatters live alongside it (`format.ts`, `currency.ts`, `numeric-input.ts` — the last also carries the amount-input separator helpers), and the locale-bound hook is `create-formatters.ts` (pure factory) + `formatters.ts` (`useFormatters()`, client) + `formatters-server.ts` (`getFormatters()`, `server-only`). Components format via the hook — see web-components-pages "Formatting & locale". Adding a language is one registry entry plus a matching `translations/<code>.json`. The next-intl framework config stays at its required root path `i18n/request.ts` (not under `lib/`).

## Directory layout (apps/web/)

```
app/
├── layout.tsx
├── error.tsx                # boundary for the group layouts themselves
├── global-error.tsx         # replaces the root layout when it throws
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
│   ├── error.tsx            # boundary inside the shell ((auth)/ and (public)/ have their own too)
│   ├── _components/         # shared across all protected pages (e.g. page-header.tsx, page-skeleton.tsx)
│   └── <route>/
│       ├── page.tsx (+ _components/, actions.ts, schema.ts, etc.)
│       └── loading.tsx      # <PageSkeleton …/> — required for every protected page
lib/                         # Auth, API, shared utils
config/
└── routes.ts                # ROUTES, AUTH_ROUTES, LOGIN_ROUTE
translations/                # en.json, es.json
packages/ui                  # Workspace — shared React components
```
