---
name: web-structure
description: Frontend app structure and where to create files (pages, components, lib, config). Use when adding routes, pages, or organizing code in apps/web.
---

# Web structure (Renly frontend)

## App Router layout

- **`app/(auth)/`** — Route group for the sign-in surface: login, signup, forgot-password, reset-password, verify-email, join (a group invite). Layout does not require a session. Each path is in `AUTH_ROUTES`.
- **`app/(public)/`** — Route group for the marketing, help and legal pages: the landing (`(public)/page.tsx` — there is no root `app/page.tsx`), help, privacy, terms, disclaimer. Reachable logged in or out, so the layout has no session gate; the site header adapts its CTAs to the session instead. Its own components live in `(public)/_components/`. Each path is in `PUBLIC_ROUTES`.
- **`app/(protected)/`** — Route group for authenticated routes: dashboard, settings, etc. Layout calls `getSession()` and redirects to `LOGIN_ROUTE` when there is no valid session. `PROTECTED_ROUTES` is not a list you edit: `config/routes.ts` computes it as every route minus the auth and public ones.
- **`app/api/`** — Route handlers, and only NextAuth's today (`app/api/auth/[...nextauth]/route.ts`). The app's data comes from the FastAPI backend through `lib/api/` and server actions, not from Next route handlers; add one only for something that must be an HTTP endpoint of the web app itself.
- **`app/layout.tsx`** — Root layout. Route groups each have their own `layout.tsx` for shared wrapper (e.g. auth layout, public site shell, protected layout with session check). `app/_components/` holds the few root-level pieces (the not-found content).
- **Error boundaries — one per surface, plus two fallbacks, and a failed read is meant to reach one.** Each route group has its own `error.tsx`, rendered INSIDE that group's layout so the visitor keeps the chrome they were using: `(protected)/error.tsx` keeps the sidebar and mobile bar, `(public)/error.tsx` the site header and footer, `(auth)/error.tsx` the auth column (with a home link, since it has no nav). `app/error.tsx` catches the group LAYOUTS themselves (a segment's `error.tsx` sits inside its layout, so a protected-layout failure lands there). `app/global-error.tsx` replaces the root layout when that throws: it resolves the locale itself (`resolveLocale` in `lib/i18n/locales.ts`, the same rule `i18n/request.ts` uses — minus the signed-in user's manual pin, which `request.ts` reads from their settings on document loads and a client component cannot, so it follows the cookie that carries the pin) and renders copy it imports STATICALLY, so it can never render empty — which is why `common.errorBoundary` lives in its own small `translations/error-boundary/<code>.json` (exported as `ERROR_BOUNDARY_MESSAGES` from `lib/i18n/error-boundary-messages.ts`, and merged into `common` by `i18n/request.ts` for every other render) rather than in the main files, which are too large to ship to every page. All of them render `ErrorState` (`components/error-state.tsx`), whose retry is `router.refresh()` + `reset()` in one transition (`reset()` alone re-renders the failed payload), and report through `useReportBoundaryError` (a caught error never reaches the browser SDK's global handler; one with a `digest` was already reported on the server). `tests/unit/error-boundary-coverage.test.ts` derives the route groups and fails on one without its boundary.
- **Loading states — every protected `page.tsx` has a `loading.tsx` in its OWN directory**, rendering `PageSkeleton` (`app/(protected)/_components/page-skeleton.tsx`) and nothing else. Own directory, not an ancestor's: Next shows the NEAREST boundary, so a parent's `loading.tsx` paints the parent page's header over the child. And a `loading.tsx` must not share its directory with a NESTED route either: it is the boundary for everything beneath it, and a production build prefetches a dynamic route only down to the first loading boundary under the segment it shares with the current page — so a list page's skeleton painted over its details (`/alerts` → `/accounts/1` showed the accounts list). A list page with routes under it lives in a route group with its `loading.tsx` (`accounts/(list)/`, `admin/(invites)/`, `shared/(groups)/`, `shared/[groupId]/(hub)/`, `shared/pots/[id]/(pot)/`), which wraps that one page and changes no URL; its `_components/`, `<feature>-actions.ts` and the like stay in the section directory. Pass `namespace` when the page's header is `t('title')` / `t('subtitle')` from that namespace, and omit it when the title is data (an account's name, a pot's label); pick `body` (`table` / `dashboard` / `form` / `sections`) plus `backLink` / `loose` to match the page's frame, so the swap moves nothing. A list page passes `toolbar` as its `EntityListToolbar`'s controls in order — `filters` and `actions`, each `{ kind, label }` with a translation KEY — and the skeleton lays them out with the toolbar's own classes (`components/entity-list-toolbar-layout.ts`, which `EntityListToolbar` renders from too) and sizes each by its real text, so the placeholder row wraps exactly where the real one does in either language; a dashboard with the period picker passes `periodPicker="header"` (beside the header) or `"toolbar"` (the investor dashboard's search + picker row). Controls only some accounts see (the scope pill, the collections filter) and dismissible hints stay out: a loading state cannot know them. `tests/e2e/loading-layout.auth.spec.ts` holds each list toolbar and each page rendering `<DashboardPeriodPicker` (derived) to within 2px of its placeholder at 390 and 1280, in both locales, and `loading-nested-routes.auth.spec.ts` asserts that entering every nested route from another section paints that route's own loading state — identified by everything its `loading.tsx` declares (heading, `body`, back link, spacing, toolbar and picker kinds, which `PageSkeletonView` reports as `data-*` on its root), not by the heading alone, and refusing any pair whose declarations are indistinguishable — both against a production build (they skip themselves on a dev server, which prefetches no loading state). `tests/unit/route-loading-coverage.test.ts` derives the route list from the filesystem and enforces all of this.

## Where to create files

- **New page (route):** Add a folder under `app/(auth)/`, `app/(public)/` or `app/(protected)/` with `page.tsx`. Add the path to `config/routes.ts` (e.g. `ROUTES.settings`) — and to `AUTH_ROUTES` or `PUBLIC_ROUTES` when it is not protected — and use that constant for links and redirects — do not hardcode URLs.
- **Page-specific components:** In `_components/` next to the page, e.g. `app/(auth)/login/_components/login-card.tsx`. Only that page (and its children) should import these.
- **Shared across all protected pages:** In `app/(protected)/_components/`, e.g. `page-header.tsx`. For components used by more than one protected route but not outside it.
- **Shared logic (auth, API, utils):** `lib/` — anything used by more than one route or shared between server and client. Which part of `lib/`:
  - **`lib/<topic>.ts`** owns one product concept's logic — its rules, derivations and the helpers around it (`lib/pots.ts`, `lib/reconciliation.ts`, `lib/money.ts`, `lib/list-scope.ts`, `lib/notifications.ts`, `lib/auth.ts`). If the file is ABOUT a feature or an entity, it goes here.
  - **`lib/utils/<name>.ts`** holds small generic helpers that know no product concept — date and period math, pagination ranges, category sorting, a safe redirect path, page metadata (`lib/utils/dates.ts`, `lib/utils/pagination.ts`, `lib/utils/safe-next-path.ts`, `lib/utils/page-metadata.tsx`).
  - The other `lib/` subfolders are named homes, below: `api/`, `hooks/`, `constants/`, `i18n/`, `fonts/`, `stores/`, `sample-data/`.
- **Client state stores:** `lib/stores/<name>-store.ts` — a zustand store for client state several components share across a page (today only `currency-store.ts`: the display currency, mirrored to a cookie so a server render reads the same value). Prefer URL params or server props; reach for a store only when neither fits.
- **Client hooks:** `lib/hooks/<name>.ts` — reusable `'use client'` hooks used by 2+ components (e.g. `use-search-params-navigation.ts`, `use-table-sort.ts`, `use-entity-form-dialog.ts`, `use-deferred-dialog-swap.ts`). One hook per file, kebab-case file named after the hook.
- **Server-side data fetching (reads):** `lib/api/<feature>.ts` with `import 'server-only'`. Used directly in server components (`page.tsx`). Can be imported by multiple pages.
- **Cross-entity API contract types:** `lib/api/types.ts` (e.g. `SortOrder`) — shared by multiple `lib/api/<feature>.ts` modules; entity-specific types stay in their feature module.
- **Server mutations:** `<feature>-actions.ts` colocated with the page (`'use server'`), e.g. `investments/investments-actions.ts`, `login/login-actions.ts`; a component's own action sits beside it in `_components/` (`feedback-actions.ts`). Called from client components. Feature-specific; do not put in `lib/`. (`notifications/actions.ts` is the one file still on the old bare name.)
- **Form schemas:** the zod schema is `<feature>-form-schema.ts` beside the form's page (`form-schema.ts` in the single-form auth routes and `admin/`). There is no `schema.ts`.
- **Used on multiple pages (this app only):** Put in the app's `components/` folder.
- **Reusable across apps (design system):** Put in `packages/ui/src/components`, add to the package's `index.ts`, and import from `@repo/ui/components` in the web app.
- **Routes:** `config/routes.ts` for `ROUTES`, `AUTH_ROUTES`, `LOGIN_ROUTE`, `PUBLIC_ROUTES`/`PROTECTED_ROUTES`, and the help-page anchors any in-app deep link must come from (`HELP_ANCHORS` + `helpAnchorPath`).
- **Sidebar navigation:** `config/nav.ts` — what the sidebar lists, as data: the groups (`FINANCES_GROUP`, `COMMITMENTS_GROUP`, …) of `{ key, href, icon }` items, `href` from `ROUTES` and `key` naming a `sidebar.nav.*` label. A new sidebar item is an entry here plus that label in both locales; `SIDEBAR_NAV_KEYS` lets `tests/unit/translations-parity.test.ts` fail on an item without one. It lives in `config/` rather than in the sidebar because the sidebar is a client module a node test cannot import. The rest of `config/` is `constants.ts` (app-wide cookie names, ids) and `site.ts` (site name, social-card defaults).
- **Type declarations:** `types/` for module augmentation (`types/next-auth.d.ts` adds the user's id, admin flag and API tokens to NextAuth's `Session`, `User` and `JWT`), and `types.d.ts` at the app root for ambient module declarations (`*.svg`). App types that describe data live with the code that owns them (`lib/api/<feature>.ts`, `lib/api/types.ts`), not here.
- **Fonts:** `lib/fonts/` — the typeface is self-hosted. `plus-jakarta-sans.ts` is its ONE `next/font/local` definition, imported by every document root (`app/layout.tsx` and `app/global-error.tsx`, which replaces it); the WOFF2 it loads and its SIL OFL licence (`OFL.txt`) sit beside it. Never `next/font/google`: it downloads the font while `next build` runs, so a slow fetch fails the build. `tests/unit/self-hosted-font.test.ts` enforces all three (no Google import, one loader, every `<html>` root on it).
- **Constants:** `lib/constants/<topic>.ts` — one file per topic (e.g. `animations.ts`, `currency.ts`, `charts.ts`). Only for constants imported by 2+ files. Single-file constants stay in the file that uses them.
- **i18n / locale:** `lib/i18n/` is the home for all locale + formatting code. `lib/i18n/locales.ts` holds the single `LOCALES` registry — the source of truth every locale-derived value flows from (`Locale`/`TextDirection` types, `DEFAULT_LOCALE`, `SUPPORTED_LOCALES`, `getLocaleTag`, `getDateFnsLocale`, `getLocaleDirection`, `LANGUAGE_OPTIONS`, `LANGUAGE_MODE_*`, `LOCALE_COOKIE`, `pinnedLocale`, browser-language detection). The pure formatters live alongside it (`format.ts`, `currency.ts`, `numeric-input.ts` — the last also carries the amount-input separator helpers), and the locale-bound hook is `create-formatters.ts` (pure factory) + `formatters.ts` (`useFormatters()`, client) + `formatters-server.ts` (`getFormatters()`, `server-only`). Components format via the hook — see web-components-pages "Formatting & locale". Adding a language is one registry entry plus a matching `translations/<code>.json`. The next-intl framework config stays at its required root path `i18n/request.ts` (not under `lib/`).

## Directory layout (apps/web/)

```
app/
├── layout.tsx
├── error.tsx                # boundary for the group layouts themselves
├── global-error.tsx         # replaces the root layout when it throws
├── not-found.tsx
├── _components/             # root-level pieces (not-found content)
├── api/auth/[...nextauth]/  # the only route handler (NextAuth)
├── (auth)/                  # No session required
│   ├── layout.tsx
│   ├── error.tsx
│   ├── login/
│   │   ├── page.tsx
│   │   ├── login-actions.ts
│   │   ├── form-schema.ts
│   │   └── _components/
│   └── signup/ forgot-password/ reset-password/ verify-email/ join/
├── (public)/                # Landing, help, legal — no session gate
│   ├── layout.tsx
│   ├── error.tsx
│   ├── page.tsx             # the landing
│   ├── _components/
│   └── help/ privacy/ terms/ disclaimer/
├── (protected)/             # getSession + redirect if missing
│   ├── layout.tsx
│   ├── error.tsx            # boundary inside the shell
│   ├── _components/         # shared across all protected pages (e.g. page-header.tsx, page-skeleton.tsx)
│   └── <route>/
│       ├── page.tsx (+ _components/, <feature>-actions.ts, <feature>-form-schema.ts)
│       └── loading.tsx      # <PageSkeleton …/> — required for every protected page
components/                  # used by more than one route (this app only)
lib/
├── <topic>.ts               # one product concept's logic
├── utils/                   # generic helpers with no product concept
├── api/  hooks/  constants/  i18n/  fonts/  stores/  sample-data/
config/
├── routes.ts                # ROUTES, AUTH_ROUTES, PUBLIC_ROUTES, LOGIN_ROUTE, HELP_ANCHORS
├── nav.ts                   # the sidebar's items
├── constants.ts
└── site.ts
i18n/request.ts              # next-intl config (required path)
types/                       # module augmentation (next-auth)
translations/                # en.json, es.json, error-boundary/
packages/ui                  # Workspace — shared React components
```
