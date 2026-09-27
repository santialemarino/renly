import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { expect, test } from '@playwright/test';

import { WEB_ROOT } from './helpers/list-pages';
import {
  holdNavigation,
  NO_PREFETCH_REASON,
  protectedPages,
  type ProtectedPage,
} from './helpers/loading-states';

/*
 * Entering a NESTED route from another section paints that route's own loading state — never its
 * parent's.
 *
 * A production build prefetches a dynamic route only down to the first `loading.tsx` below the segment
 * it shares with the current page. While `accounts/loading.tsx` sat beside `accounts/[id]/`, going
 * from /alerts to /accounts/1 painted the ACCOUNTS LIST's skeleton — its header, its toolbar — over a
 * page about one account, and /dashboard → /shared/pots/999 painted the groups list's. The detail's
 * own `loading.tsx` was there all along and never shown. Each such list page now lives in a route
 * group, and the unit guard in `route-loading-coverage.test.ts` refuses a `loading.tsx` that shares
 * its directory with a nested route; this spec is the runtime side, which only a real navigation on
 * a production build can show.
 *
 * The population is derived: every protected page whose URL sits under another page's URL. The
 * expected heading comes from the route's own `loading.tsx` (its namespace's title, or no heading at
 * all when the title is data), and the parent's title must not be on screen. Dynamic segments get an
 * id that does not exist — the page then 404s, but only the loading state in front of it is read.
 */

// Read rather than imported: Playwright's loader requires an import attribute for JSON.
const en: unknown = JSON.parse(readFileSync(join(WEB_ROOT, 'translations', 'en.json'), 'utf8'));

type Title = string | null;

// The heading a route's loading state paints: its namespace's title, or none.
function loadingTitle(page: ProtectedPage): Title {
  const loading = readFileSync(join(WEB_ROOT, dirname(page.file), 'loading.tsx'), 'utf8');
  const namespace = /<PageSkeleton\b[^>]*\bnamespace="([^"]+)"/.exec(loading)?.[1];
  if (!namespace) return null;
  const title = namespace
    .split('.')
    .reduce<unknown>((node, key) => (node as Record<string, unknown>)?.[key], en) as {
    title?: unknown;
  };
  expect(typeof title?.title, `${namespace}.title`).toBe('string');
  return title.title as string;
}

const PAGES = protectedPages();
const NESTED = PAGES.flatMap((page) => {
  const parent = PAGES.filter(
    (other) => other !== page && page.route.startsWith(`${other.route}/`),
  ).sort((a, b) => b.route.length - a.route.length)[0];
  return parent ? [{ page, parent }] : [];
});

test.describe('nested routes paint their own loading state (signed in)', () => {
  test.describe.configure({ timeout: 120_000 });

  test('derives the nested routes, detail pages and their wizards alike', () => {
    const routes = NESTED.map(({ page }) => page.route);
    expect(routes).toEqual(
      expect.arrayContaining([
        '/accounts/999999',
        '/shared/999999',
        '/shared/pots/999999/take-out',
      ]),
    );
  });

  for (const { page: target, parent } of NESTED) {
    test(`${parent.route} → ${target.route}`, async ({ page }) => {
      await page
        .context()
        .addCookies([{ name: 'NEXT_LOCALE', value: 'en', domain: 'localhost', path: '/' }]);
      await page.setViewportSize({ width: 1280, height: 900 });

      const expected = loadingTitle(target);
      const parentTitle = loadingTitle(parent);
      const measured = await holdNavigation(
        page,
        target.route,
        async () => page.getByTestId('page-skeleton').locator('h1').allInnerTexts(),
        async () => null,
      );
      test.skip(measured === null, NO_PREFETCH_REASON);

      const headings = measured!.held;
      if (parentTitle !== null && parentTitle !== expected) {
        expect(headings, `${target.route} painted ${parent.route}'s loading state`).not.toContain(
          parentTitle,
        );
      }
      expect(headings).toEqual(expected === null ? [] : [expected]);
    });
  }
});
