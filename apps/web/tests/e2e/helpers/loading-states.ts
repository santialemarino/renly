import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { expect, type Page, type Request, type Route } from '@playwright/test';

import { ROUTES } from '@/config/routes';
import { WEB_ROOT } from './list-pages';

/*
 * What the loading-state specs share: the protected pages (derived from the route tree), the hints to
 * dismiss before measuring, and the one mechanism that can hold a route's loading state on screen.
 *
 * That mechanism: a production build prefetches every route's `loading.tsx` ahead of the navigation,
 * so while the NAVIGATION's own RSC request is held, the router shows the prefetched fallback and
 * nothing else. A dev server prefetches nothing — there is then no fallback to show until the whole
 * response arrives — so `holdNavigation` reports that (null) instead of pretending it measured.
 */

const PROTECTED = join(WEB_ROOT, 'app', '(protected)');
export const NAV_TIMEOUT = 30_000;
// How long to wait for the router's prefetch before concluding this server does not prefetch.
const PREFETCH_WAIT_MS = 5_000;

// Where a navigation starts: a protected page that is none of the measured ones.
export const START = ROUTES.alerts;

// A dynamic segment's stand-in: no such record exists, which is fine — only the loading state is read.
export const MISSING_ID = '999999';

export interface ProtectedPage {
  // Path of the page.tsx, relative to apps/web.
  file: string;
  // The URL it serves: route groups dropped, dynamic segments filled with `MISSING_ID`.
  route: string;
}

// Every page under app/(protected), with the URL it serves.
export function protectedPages(): ProtectedPage[] {
  const out: ProtectedPage[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry === 'page.tsx') {
        const segments = relative(PROTECTED, dir)
          .split(sep)
          .filter((segment) => segment && !/^\(.*\)$/.test(segment))
          .map((segment) => (segment.startsWith('[') ? MISSING_ID : segment));
        out.push({ file: relative(WEB_ROOT, full), route: `/${segments.join('/')}` });
      }
    }
  };
  walk(PROTECTED);
  return out.sort((a, b) => a.route.localeCompare(b.route));
}

/*
 * Every dismissible hint's storage key in the app, so a spec can measure the layout without them. Read
 * as every `'…-dismissed'` string literal, the one naming convention the keys share — a hint whose key
 * lives in a constant (`STORAGE_KEY = 'currency-hint-dismissed'`) is found like an inline one.
 */
export function allHintKeys(): string[] {
  const keys = new Set<string>();
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (entry === 'node_modules' || entry.startsWith('.')) continue;
      if (statSync(full).isDirectory()) walk(full);
      else if (entry.endsWith('.tsx')) {
        for (const match of readFileSync(full, 'utf8').matchAll(
          /['"]([a-z0-9-]+-dismissed)['"]/g,
        )) {
          keys.add(match[1]!);
        }
      }
    }
  };
  walk(join(WEB_ROOT, 'app'));
  walk(join(WEB_ROOT, 'components'));
  return [...keys];
}

// Dismisses every hint before the page loads (hints reveal with a height animation after load).
export async function dismissAllHints(page: Page) {
  await page.addInitScript((keys) => {
    for (const key of keys) localStorage.setItem(key, 'true');
  }, allHintKeys());
}

// The RSC request a navigation makes (not a prefetch) — the one that carries the page's content.
function isNavigationRequest(req: Request, route: string): boolean {
  const headers = req.headers();
  return (
    new URL(req.url()).pathname === route &&
    headers['rsc'] === '1' &&
    !headers['next-router-prefetch']
  );
}

function isPrefetchRequest(req: Request, route: string): boolean {
  return new URL(req.url()).pathname === route && Boolean(req.headers()['next-router-prefetch']);
}

/*
 * From `START`, navigates to `route` with its content held back and runs `whileHeld` while only the
 * prefetched loading state can be on screen; then releases the content and runs `afterRelease` once
 * that loading state is gone. Returns null when this server never prefetched the route (a dev server).
 */
export async function holdNavigation<Held, Released>(
  page: Page,
  route: string,
  whileHeld: () => Promise<Held>,
  afterRelease: () => Promise<Released>,
): Promise<{ held: Held; released: Released } | null> {
  await page.goto(START);
  await expect(page.locator('main h1').first()).toBeVisible({ timeout: NAV_TIMEOUT });

  let release = () => {};
  const released = new Promise<void>((resolve) => (release = resolve));
  const handler = async (intercepted: Route) => {
    if (isNavigationRequest(intercepted.request(), route)) await released;
    await intercepted.continue();
  };
  await page.route((url) => url.pathname === route, handler);

  try {
    const prefetched = page
      .waitForRequest((req) => isPrefetchRequest(req, route), { timeout: PREFETCH_WAIT_MS })
      .then(
        () => true,
        () => false,
      );
    await page.evaluate((target) => {
      (
        window as unknown as { next: { router: { prefetch(r: string): void } } }
      ).next.router.prefetch(target);
    }, route);
    if (!(await prefetched)) return null;
    // Let the prefetch's response land in the router cache before navigating.
    await page.waitForLoadState('networkidle');

    await page.evaluate((target) => {
      (window as unknown as { next: { router: { push(r: string): void } } }).next.router.push(
        target,
      );
    }, route);
    await expect(page.getByTestId('page-skeleton')).toBeVisible({ timeout: NAV_TIMEOUT });
    const held = await whileHeld();

    release();
    await expect(page.getByTestId('page-skeleton')).toHaveCount(0, { timeout: NAV_TIMEOUT });
    return { held, released: await afterRelease() };
  } finally {
    release();
    await page.unroute((url) => url.pathname === route, handler);
  }
}

// The reason a spec gives when `holdNavigation` could not hold anything.
export const NO_PREFETCH_REASON =
  'this server does not prefetch loading states (a dev server), so none can be held on screen';
