import { existsSync, readFileSync } from 'node:fs';
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
 * The population is derived: every protected page whose URL sits under another page's URL. What
 * identifies a skeleton is everything its `loading.tsx` declares — the heading (its namespace's title,
 * or none when the title is data), the body kind, the back link, the spacing, the toolbar and the
 * period picker — read from the declaration and compared with what `PageSkeletonView` reports about
 * itself on screen. The heading alone is not enough: a pot page and its three wizards all open on a
 * data title, so a check of headings passed whichever of them painted. The self-check below fails if
 * any covered pair is indistinguishable, so that cannot happen again silently. Dynamic segments get an
 * id that does not exist — the page then 404s, but only the loading state in front of it is read.
 */

// Read rather than imported: Playwright's loader requires an import attribute for JSON.
const en: unknown = JSON.parse(readFileSync(join(WEB_ROOT, 'translations', 'en.json'), 'utf8'));

// What a skeleton reports about itself, as `PageSkeletonView` renders it on its root.
interface Signature {
  heading: string | null;
  body: string;
  backLink: string;
  loose: string;
  toolbar: string;
  period: string;
}

// The heading a namespace paints: its English title.
function namespaceTitle(namespace: string): string {
  const node = namespace
    .split('.')
    .reduce<unknown>((at, key) => (at as Record<string, unknown>)?.[key], en) as {
    title?: unknown;
  };
  expect(typeof node?.title, `${namespace}.title`).toBe('string');
  return node.title as string;
}

/*
 * The `loading.tsx` that governs a page: the nearest one at or above its directory, the way Next
 * resolves a loading boundary. For a target that is its own (the unit guard requires one); for a
 * parent it is whichever would paint — which, when a parent's loading state has been moved up, is the
 * moved one, so the comparison below still names the right culprit instead of failing to read a file.
 */
function governingLoading(page: ProtectedPage): string {
  for (let dir = dirname(page.file); dir.includes('(protected)'); dir = dirname(dir)) {
    const path = join(WEB_ROOT, dir, 'loading.tsx');
    if (existsSync(path)) return readFileSync(path, 'utf8');
  }
  throw new Error(`no loading.tsx governs ${page.file}`);
}

// The skeleton that governs a route, read from its `<PageSkeleton …/>` tag.
function declaredSignature(page: ProtectedPage): Signature {
  const loading = governingLoading(page);
  const start = loading.indexOf('<PageSkeleton');
  const tag = loading.slice(start, loading.indexOf('/>', start));
  const namespace = /\bnamespace="([^"]+)"/.exec(tag)?.[1];
  return {
    heading: namespace ? namespaceTitle(namespace) : null,
    body: /\bbody="([^"]+)"/.exec(tag)?.[1] ?? 'missing',
    backLink: String(/\bbackLink\b/.test(tag)),
    loose: String(/\bloose\b/.test(tag)),
    toolbar: /\btoolbar="add-only"/.test(tag)
      ? 'add-only'
      : /\btoolbar=\{/.test(tag)
        ? 'list'
        : 'none',
    period: /\bperiodPicker="([^"]+)"/.exec(tag)?.[1] ?? 'none',
  };
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

  test("tells every nested route's skeleton apart from its parent's", () => {
    // A pair that declares the same skeleton could never fail the check below — refuse it here.
    const same = NESTED.filter(
      ({ page, parent }) =>
        JSON.stringify(declaredSignature(page)) === JSON.stringify(declaredSignature(parent)),
    ).map(({ page, parent }) => `${parent.route} → ${page.route}`);
    expect(same, 'nested routes whose loading state is indistinguishable from the parent').toEqual(
      [],
    );
  });

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

      // The target's own loading state, not an ancestor's standing in for it.
      expect(existsSync(join(WEB_ROOT, dirname(target.file), 'loading.tsx'))).toBe(true);
      const expected = declaredSignature(target);
      const measured = await holdNavigation(
        page,
        target.route,
        async (): Promise<Signature> => {
          const skeleton = page.getByTestId('page-skeleton');
          const headings = await skeleton.locator('h1').allInnerTexts();
          const attr = async (name: string) => (await skeleton.getAttribute(name)) ?? 'missing';
          return {
            heading: headings[0] ?? null,
            body: await attr('data-body'),
            backLink: await attr('data-back-link'),
            loose: await attr('data-loose'),
            toolbar: await attr('data-toolbar'),
            period: await attr('data-period'),
          };
        },
        async () => null,
      );
      test.skip(measured === null, NO_PREFETCH_REASON);

      const painted = measured!.held;
      expect(
        painted,
        JSON.stringify(painted) === JSON.stringify(declaredSignature(parent))
          ? `${target.route} painted ${parent.route}'s loading state`
          : `${target.route} painted a loading state that is not its own`,
      ).toEqual(expected);
    });
  }
});
