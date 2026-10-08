import { existsSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

/*
 * Which pages the text sweep (`locale-text-clipping.auth.spec.ts`) visits: EVERY page of the app
 * surface, derived by walking `app/(protected)` for `page.tsx` files, minus the skips below. Nothing
 * is listed by hand, so a new page joins the sweep by existing. Spanish runs 20-30% longer than
 * English, and the defect class is copy that fits in one language and not in the other — any page
 * can carry it.
 *
 * A dynamic route has no URL without an id. It is swept when the seed can give it one (`DYNAMIC_URLS`
 * in the spec) and must otherwise be skipped here with its reason; `tests/unit/text-sweep-coverage.test.ts`
 * holds the two lists to the derived population in both directions.
 */

const APP_ROOT = join(import.meta.dirname, '..', '..', '..', 'app');
const PROTECTED = join(APP_ROOT, '(protected)');

// Pages the sweep does not visit, each with the reason — never silently.
export const TEXT_SWEEP_SKIPS: Record<string, string> = {
  '/admin':
    'admin-only: a 404 for the harness account. The admin session exists (ADMIN_AUTH_STATE_PATH in helpers/auth.ts, used by the axe sweep), but this sweep does not load it yet (U12b)',
  '/admin/feedback':
    'admin-only, like /admin: needs the admin session, which this sweep does not load yet (U12b)',
  '/shared/pots/[id]/buy-out':
    'a 404 unless the pot is priced and divided (buy-out also needs a second active seat). a11y-routes.auth.spec.ts seeds such a pot, but this sweep does not use that seed yet (U12b)',
  '/shared/pots/[id]/contribute':
    'a 404 unless the pot is priced and divided, like /shared/pots/[id]/buy-out: not seeded for this sweep yet (U12b)',
  '/shared/pots/[id]/take-out':
    'a 404 unless the pot is priced and divided, like /shared/pots/[id]/buy-out: not seeded for this sweep yet (U12b)',
};

// Every page under (protected), as its route pattern: route groups dropped, dynamic segments kept.
export function protectedPageRoutes(dir = PROTECTED): string[] {
  const out: string[] = [];
  if (existsSync(join(dir, 'page.tsx'))) {
    const segments = relative(PROTECTED, dir)
      .split(sep)
      .filter((segment) => segment !== '' && !/^\(.*\)$/.test(segment));
    out.push(`/${segments.join('/')}`);
  }
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory() && !entry.startsWith('_'))
      out.push(...protectedPageRoutes(full));
  }
  return out.sort();
}

// The pages the sweep visits.
export function textSweepRoutes(): string[] {
  return protectedPageRoutes().filter((route) => !(route in TEXT_SWEEP_SKIPS));
}

// The sweep's widths: the phones the defect was measured on (360, 390), the tablet edge where the
// sidebar appears (768), and the two laptop widths every layout step sits between.
export const TEXT_SWEEP_WIDTHS = [360, 390, 768, 1024, 1280] as const;
