---
name: web-components-pages
description: How to create a component or a page in the Renly web app (Next.js App Router). Use when adding new UI, forms, or routes in apps/web.
---

# Web components and pages (Renly frontend)

## Creating a page

1. **Choose the route group:** Auth (login, signup) → `app/(auth)/<name>/`. Protected (dashboard, settings) → `app/(protected)/<name>/`.
2. **Add the path to config:** In `config/routes.ts`, add the path to `ROUTES` (e.g. `settings: '/settings'`). Use `ROUTES.*` everywhere; no hardcoded paths.
3. **Add `page.tsx`:** Default export a server component. For protected routes, the layout already ensures a session; call `getSession()` in the page if you need user data. For auth routes, redirect to `ROUTES.home` when the user is already logged in.
4. **Metadata:** Use `generatePageMetadata('namespace')` from `lib/utils/page.tsx` when the page has translations.

## Creating a component

- **Only used on one page:** Create it in that page's `_components/` folder, e.g. `app/(auth)/login/_components/login-card.tsx`.
- **Used on multiple pages:** Create it in the app's `components/` folder.
- **Reusable across apps (design system):** Create it in `packages/ui/src/components` and add it to the `index.ts`, so it can be shared. In the web app, import from `@repo/ui/components` or the path defined in the UI package.
- **Client interactivity:** Add `'use client'` at the top. Use for forms, hooks, event handlers, or anything that uses browser APIs or React state.
- **Importing:** Always import components (and everything else) using aliases defined in `package.json` - not using `.` or `..` - (e.g. `@/app/(auth)/login/_components/login-form`).

## Colocate feature files

Keep all feature-specific modules in the same folder as the page that uses them: `actions.ts`, `schema.ts`, `form-schema.ts`, etc. Same hierarchy as the route — e.g. `app/(auth)/login/actions.ts`, `app/(auth)/login/form-schema.ts`, `app/(protected)/dashboard/actions.ts`. Do not put them in a global `lib/` or `app/` root unless they are shared across multiple routes.

## Order and style

**Outside the component (file-level order):**

1. **Consts** — Module-level constants (e.g. config objects, magic numbers) at the top of the file.
2. **Metadata** — For pages only: `export const metadata = { ... }` or `export async function generateMetadata() { ... }`.
3. **Props type** — Always place it immediately above the component. Define it for every component that receives props/params; omit only when the component has no props.

**Inside the component (declaration order):**

1. **Session** — `getSession()` or similar, if the component needs it (server components).
2. **Translations** — `useTranslations('namespace')`: first the specific/feature namespace (e.g. `login`), then `tCommon` / `useTranslations('common')` if needed.
3. **Router** — `useRouter()` (client components).
4. **State and refs** — `useState`, `useForm`, `useRef`, `useWatch`, etc.
5. **Derived state / memo** — `useMemo`, computed values that depend on the above.
6. **Effects** — `useEffect` (and similar).
7. **Handlers and functions** — `onSubmit`, event handlers, and other callbacks.
8. **Early returns** — Guard clauses (e.g. loading, null checks).
9. **Return** — The JSX return last.

Keep the page thin: put UI in components. One main component per file; small helpers can live in the same file or a sibling. Use `ROUTES` and translation keys consistently.

## Comments

There are no strict rules. Add comments in a tidy way where they clarify something non-obvious or worth explaining — on components, types, methods, etc. Most importantly: **follow the commenting style you see in the codebase**, and in particular in that folder or feature (e.g. the same route group or set of pages). Match existing style rather than introducing a new one.
