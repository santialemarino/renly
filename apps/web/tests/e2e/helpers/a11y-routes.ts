import {
  accountLedgerPath,
  AUTH_ROUTES,
  PROTECTED_ROUTES,
  PUBLIC_ROUTES,
  ROUTES,
  sharedBuyOutPath,
  sharedContributePath,
  sharedGroupPath,
  sharedPotPath,
  sharedSharePath,
  sharedTakeOutPath,
} from '@/config/routes';

/*
 * Which pages the accessibility sweep scans, derived from `config/routes.ts` rather than listed.
 *
 * Pure data, no Playwright import, because `tests/unit/a11y-sweep-coverage.test.ts` reads it too: it
 * walks every `page.tsx` under `app/` and fails unless each one's route is swept here or skipped here
 * with its reason. A new route added to `ROUTES` is swept the day it is added; a new page added
 * without one — a dynamic route, say — fails that test until it is placed.
 */

// Signed out: the public pages and every auth page, in whatever state each renders with no token.
export const SIGNED_OUT_ROUTES: readonly string[] = [...PUBLIC_ROUTES, ...AUTH_ROUTES];

// Pages the sweep does not scan, each with the reason — never silently. Empty today.
export const A11Y_SWEEP_SKIPS: Record<string, string> = {};

/*
 * The admin-only routes: every protected route under `ROUTES.admin`. They render only for a user with
 * `users.is_admin` (anyone else gets the not-found page), so they are scanned with the ADMIN session
 * (`ADMIN_AUTH_STATE_PATH`), not the harness one.
 */
export const ADMIN_ROUTES: readonly string[] = PROTECTED_ROUTES.filter(
  (route) => route === ROUTES.admin || route.startsWith(`${ROUTES.admin}/`),
);

/*
 * Signed in: every protected route but the admin ones, plus the public pages (their header changes for
 * a signed-in visitor) and the invite landing, the one auth route that does not send a signed-in
 * visitor away.
 */
export const SIGNED_IN_ROUTES: readonly string[] = [
  ...PROTECTED_ROUTES.filter(
    (route) => !ADMIN_ROUTES.includes(route) && !(route in A11Y_SWEEP_SKIPS),
  ),
  ...PUBLIC_ROUTES,
  ROUTES.auth.joinGroup,
];

// The ids a signed-in sweep seeds so the dynamic routes have something to render.
export interface A11ySeedIds {
  accountId: number;
  groupId: number;
  potId: number;
}

/*
 * The dynamic routes, keyed by their `page.tsx` pattern, each with how to reach it from the seed. The
 * keys are what the coverage test matches against the route tree.
 */
export const DYNAMIC_ROUTES: Record<string, (ids: A11ySeedIds) => string> = {
  '/accounts/[id]': ({ accountId }) => accountLedgerPath(accountId),
  '/shared/[groupId]': ({ groupId }) => sharedGroupPath(groupId),
  '/shared/[groupId]/share': ({ groupId }) => sharedSharePath(groupId),
  '/shared/pots/[id]': ({ potId }) => sharedPotPath(potId),
  '/shared/pots/[id]/buy-out': ({ potId }) => sharedBuyOutPath(potId),
  '/shared/pots/[id]/contribute': ({ potId }) => sharedContributePath(potId),
  '/shared/pots/[id]/take-out': ({ potId }) => sharedTakeOutPath(potId),
};

// A path no route answers: the root not-found, rendered under the root layout alone.
export const UNKNOWN_ROUTE = '/this-route-does-not-exist';

// A real route whose page calls `notFound()` (no pot has this id): the not-found rendered INSIDE the
// app shell, a different render from UNKNOWN_ROUTE's, with the protected layout's landmarks around it.
export const IN_APP_NOT_FOUND_ROUTE = sharedPotPath(999_999);

export const A11Y_LOCALES = ['en', 'es'] as const;
