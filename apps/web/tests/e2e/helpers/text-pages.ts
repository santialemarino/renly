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
    'admin-only: the harness account is not an admin, so the page is a 404 (and in open signup mode it is a 404 for everyone)',
  '/admin/feedback': 'admin-only, like /admin',
  '/shared/[groupId]':
    'needs a group with shared money in it, which needs a second member — the fixture the money sweep is waiting on too (U12b)',
  '/shared/[groupId]/share': 'needs a group, like /shared/[groupId]',
  '/shared/pots/[id]': 'needs a pot, which needs a group',
  '/shared/pots/[id]/buy-out': 'needs a pot, which needs a group',
  '/shared/pots/[id]/contribute': 'needs a pot, which needs a group',
  '/shared/pots/[id]/take-out': 'needs a pot, which needs a group',
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
