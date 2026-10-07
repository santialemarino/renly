import { existsSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { ALL_ROUTE_PATHS } from '@/config/routes';
import {
  A11Y_SWEEP_SKIPS,
  ADMIN_ROUTES,
  DYNAMIC_ROUTES,
  SIGNED_IN_ROUTES,
  SIGNED_OUT_ROUTES,
} from '../e2e/helpers/a11y-routes';

/*
 * The accessibility sweep scans every page the app has, and the list of those pages is DERIVED here
 * from the route tree rather than trusted.
 *
 * Every folder under `app/` holding a `page.tsx` is a page, and its route is the folder path with the
 * route groups (`(protected)`, …) dropped and the dynamic segments kept as written (`/accounts/[id]`).
 * Each must be scanned by one of the two sweeps (`a11y-routes.spec.ts` signed out,
 * `a11y-routes.auth.spec.ts` signed in) or skipped with a reason in `helpers/a11y-routes.ts`. The two
 * sweeps' static lists come from `config/routes.ts`, so a route added there is swept without anyone
 * listing it; a page with no entry there — a new dynamic route — fails here until it is placed.
 */

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, '..', '..', 'app');

// Every page's route pattern.
function pageRoutes(dir = APP, segments: string[] = []): string[] {
  const out: string[] = [];
  if (existsSync(join(dir, 'page.tsx'))) out.push(`/${segments.join('/')}`);
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (!statSync(full).isDirectory() || entry.startsWith('_')) continue;
    const isGroup = entry.startsWith('(') && entry.endsWith(')');
    out.push(...pageRoutes(full, isGroup ? segments : [...segments, entry]));
  }
  return out;
}

describe('the accessibility sweep’s page list', () => {
  const pages = pageRoutes().sort();
  const swept = new Set([
    ...SIGNED_OUT_ROUTES,
    ...SIGNED_IN_ROUTES,
    ...ADMIN_ROUTES,
    ...Object.keys(DYNAMIC_ROUTES),
  ]);
  const skipped = Object.keys(A11Y_SWEEP_SKIPS);

  it('derives a real population — static, grouped and dynamic pages alike', () => {
    expect(pages).toEqual(
      expect.arrayContaining(['/', '/login', '/dashboard', '/accounts/[id]', '/shared/pots/[id]']),
    );
    expect(pages.length).toBeGreaterThan(40);
  });

  it('scans or skips every page', () => {
    expect(pages.filter((route) => !swept.has(route) && !skipped.includes(route))).toEqual([]);
  });

  it('names no route that has no page', () => {
    expect([...swept, ...skipped].filter((route) => !pages.includes(route))).toEqual([]);
  });

  it('never both scans and skips a page', () => {
    expect(skipped.filter((route) => swept.has(route))).toEqual([]);
  });

  it('gives every skip a reason', () => {
    expect(Object.entries(A11Y_SWEEP_SKIPS).filter(([, reason]) => reason.length < 40)).toEqual([]);
  });

  it('scans every admin page, and only those, with the admin session', () => {
    // The harness account gets the not-found page on an admin route, so a scan of one in the signed-in
    // sweep would pass without checking the page it names; each must be in ADMIN_ROUTES instead.
    const adminPages = pages.filter((route) => route === '/admin' || route.startsWith('/admin/'));
    expect(adminPages.length).toBeGreaterThan(0);
    expect([...ADMIN_ROUTES].sort()).toEqual(adminPages);
    expect(SIGNED_IN_ROUTES.filter((route) => ADMIN_ROUTES.includes(route))).toEqual([]);
  });

  it('takes the static routes from config/routes.ts, not a list of its own', () => {
    // Every static route the config declares is scanned or skipped, so the derivation above cannot be
    // satisfied by a sweep that quietly dropped one the config still has.
    expect(
      ALL_ROUTE_PATHS.filter((route) => !swept.has(route) && !skipped.includes(route)),
    ).toEqual([]);
  });
});
