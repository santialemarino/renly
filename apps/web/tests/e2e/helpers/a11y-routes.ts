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

// Pages the sweep does not scan, each with the reason — never silently.
export const A11Y_SWEEP_SKIPS: Record<string, string> = {
  [ROUTES.admin]:
    'admin-only: the harness account is not an admin, so this route shows it the not-found page (scanned at UNKNOWN_ROUTE) and the invite admin itself would go unscanned — a scan here would pass without checking the page it names',
  [ROUTES.adminFeedback]:
    'admin-only, for the same reason as /admin: the harness account gets the not-found page, never the feedback admin',
};

/*
 * Signed in: every protected route, plus the public pages (their header changes for a signed-in
 * visitor) and the invite landing, the one auth route that does not send a signed-in visitor away.
 */
export const SIGNED_IN_ROUTES: readonly string[] = [
  ...PROTECTED_ROUTES.filter((route) => !(route in A11Y_SWEEP_SKIPS)),
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

// A path no route answers, for the not-found page each surface renders.
export const UNKNOWN_ROUTE = '/this-route-does-not-exist';

export const A11Y_LOCALES = ['en', 'es'] as const;
