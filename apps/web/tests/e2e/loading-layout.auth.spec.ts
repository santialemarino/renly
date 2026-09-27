import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { expect, request, test, type Page, type Request, type Route } from '@playwright/test';

import { ROUTES } from '@/config/routes';
import { API_BASE, apiToken } from './helpers/api';
import { listPages, WEB_ROOT } from './helpers/list-pages';

/*
 * A route's loading state must not move the page when the real content replaces it.
 *
 * `PageSkeleton` paints each page's frame while its reads are in flight: the real header, then
 * placeholders standing where the toolbar and the content will be. The defect this pins: at 390px the
 * placeholder toolbar was a single row while the real one stacks the search, each filter and the add
 * button — so /expenses' table landed 88px lower once it loaded, and /dashboard's figures 52px lower
 * because the period picker (stacked under the header on a phone) had no placeholder at all. At
 * 1280px both lined up, which is why nothing had noticed.
 *
 * How the loading state is held on screen: a production build prefetches every route's `loading.tsx`
 * ahead of the navigation, so while the NAVIGATION's own RSC request is held, the router shows the
 * prefetched fallback and nothing else. The spec holds that request, measures the placeholder, lets it
 * go, and measures the element that replaced it. A dev server prefetches nothing — there is then no
 * fallback to show until the whole response arrives — so the spec skips itself there, saying why,
 * rather than reporting a pass it never measured. CI runs it against the production build.
 *
 * The population: every list page (derived, see `helpers/list-pages.ts`) measured at its toolbar, and
 * the two dashboards whose header carries the period picker, measured at the picker.
 *
 * Two things a loading state cannot know are held out rather than tolerated, both derived from source:
 * a control only some accounts see (the scope pill for a group member, the collections filter once a
 * collection exists — the route is skipped, saying so, when this account has either), and a
 * dismissible hint above the toolbar, which reveals itself with a height animation after the page
 * loads by design (the spec dismisses the page's own hints first, so it measures the layout without).
 */

const WIDTHS = [390, 1280] as const;
const LOCALES = ['en', 'es'] as const;

// Sub-pixel rounding only. A real mismatch is a whole control's height (32-36px) or more.
const TOLERANCE_PX = 2;
const NAV_TIMEOUT = 30_000;
// How long to wait for the router's prefetch before concluding this server does not prefetch.
const PREFETCH_WAIT_MS = 5_000;
// Motion's `layout` animations settle within ANIMATION_DEFAULT (250ms); measure after they have.
const SETTLE_MS = 600;

// Where a navigation starts: a protected page that is none of the measured ones.
const START = ROUTES.alerts;

interface Target {
  route: string;
  // The page's own file, relative to apps/web.
  file: string;
  // The loading state's placeholder, and the element that replaces it.
  skeleton: string;
  real: string;
}

type AccountDependency = 'groups' | 'collections';
type AccountState = Record<AccountDependency, boolean>;

// The source of a page and of the components beside it, which is where its toolbar lives.
function routeSource(target: Target): string {
  const components = join(WEB_ROOT, dirname(target.file), '_components');
  const siblings = existsSync(components)
    ? readdirSync(components)
        .filter((name) => name.endsWith('.tsx'))
        .map((name) => readFileSync(join(components, name), 'utf8'))
    : [];
  return [readFileSync(join(WEB_ROOT, target.file), 'utf8'), ...siblings].join('\n');
}

// Which account-dependent controls this route's toolbar can render.
function dependencies(target: Target): AccountDependency[] {
  const source = routeSource(target);
  return [
    ...(source.includes('<ScopePill') ? (['groups'] as const) : []),
    ...(source.includes('<CollectionMultiSelect') ? (['collections'] as const) : []),
  ];
}

// The dismissible hints the page renders itself: its `storageKey` literals.
function hintKeys(target: Target): string[] {
  const page = readFileSync(join(WEB_ROOT, target.file), 'utf8');
  return [...page.matchAll(/storageKey="([^"]+)"/g)].map((match) => match[1]!);
}

const TARGETS: Target[] = [
  ...listPages().map(({ route, file }) => ({
    route,
    file,
    skeleton: '[data-testid="page-skeleton-toolbar"]',
    real: '[data-testid="entity-list-toolbar"]',
  })),
  ...[
    { route: ROUTES.home, file: 'app/(protected)/dashboard/page.tsx' },
    { route: ROUTES.financeDashboard, file: 'app/(protected)/finance-dashboard/page.tsx' },
  ].map((page) => ({
    ...page,
    skeleton: '[data-testid="page-skeleton-period"]',
    real: '[data-testid="dashboard-period-picker"]',
  })),
];

// Whether this account has a group / a collection — each adds a toolbar control the skeleton omits.
async function accountState(): Promise<AccountState> {
  const token = await apiToken();
  const context = await request.newContext({
    baseURL: API_BASE,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  try {
    const [groups, collections] = await Promise.all([
      context.get('/groups'),
      context.get('/collections'),
    ]);
    expect(groups.ok() && collections.ok(), 'reading the account state failed').toBe(true);
    return {
      groups: ((await groups.json()) as unknown[]).length > 0,
      collections: ((await collections.json()) as unknown[]).length > 0,
    };
  } finally {
    await context.dispose();
  }
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

async function box(page: Page, selector: string) {
  const found = page.locator(selector).first();
  await expect(found).toBeVisible({ timeout: NAV_TIMEOUT });
  const rect = await found.boundingBox();
  expect(rect, `${selector} has no box`).not.toBeNull();
  return { top: rect!.y, bottom: rect!.y + rect!.height };
}

/*
 * Navigates to `target.route` with its content held back, measures the placeholder, releases the
 * content and measures what replaced it. Returns null when this server never prefetched the route —
 * i.e. a dev server, where no loading state can be held on screen.
 */
async function measure(page: Page, target: Target) {
  await page.goto(START);
  await expect(page.locator('main h1').first()).toBeVisible({ timeout: NAV_TIMEOUT });

  let release = () => {};
  const released = new Promise<void>((resolve) => (release = resolve));
  const handler = async (route: Route) => {
    if (isNavigationRequest(route.request(), target.route)) await released;
    await route.continue();
  };
  await page.route((url) => url.pathname === target.route, handler);

  try {
    const prefetched = page
      .waitForRequest((req) => isPrefetchRequest(req, target.route), { timeout: PREFETCH_WAIT_MS })
      .then(
        () => true,
        () => false,
      );
    await page.evaluate((route) => {
      (
        window as unknown as { next: { router: { prefetch(r: string): void } } }
      ).next.router.prefetch(route);
    }, target.route);
    if (!(await prefetched)) return null;
    // Let the prefetch's response land in the router cache before navigating.
    await page.waitForLoadState('networkidle');

    await page.evaluate((route) => {
      (window as unknown as { next: { router: { push(r: string): void } } }).next.router.push(
        route,
      );
    }, target.route);
    await expect(page.getByTestId('page-skeleton')).toBeVisible({ timeout: NAV_TIMEOUT });
    await page.waitForTimeout(SETTLE_MS);
    const skeleton = await box(page, target.skeleton);

    release();
    await expect(page.getByTestId('page-skeleton')).toHaveCount(0, { timeout: NAV_TIMEOUT });
    await page.waitForTimeout(SETTLE_MS);
    const real = await box(page, target.real);
    return { skeleton, real };
  } finally {
    release();
    await page.unroute((url) => url.pathname === target.route, handler);
  }
}

test.describe('loading states keep the layout (signed in)', () => {
  test.describe.configure({ timeout: 120_000 });

  let state: AccountState;
  test.beforeAll(async () => {
    state = await accountState();
  });

  for (const locale of LOCALES) {
    for (const width of WIDTHS) {
      for (const target of TARGETS) {
        test(`${target.route} at ${width}px in ${locale}`, async ({ page }) => {
          const missing = dependencies(target).filter((key) => state[key]);
          test.skip(
            missing.length > 0,
            `this account has ${missing.join(' and ')}, which add a toolbar control no loading state can know about`,
          );

          await page
            .context()
            .addCookies([{ name: 'NEXT_LOCALE', value: locale, domain: 'localhost', path: '/' }]);
          await page.addInitScript((keys) => {
            for (const key of keys) localStorage.setItem(key, 'true');
          }, hintKeys(target));
          await page.setViewportSize({ width, height: 900 });

          const measured = await measure(page, target);
          test.skip(
            measured === null,
            'this server does not prefetch loading states (a dev server), so none can be held on screen',
          );

          const { skeleton, real } = measured!;
          expect(
            Math.abs(real.top - skeleton.top),
            `${target.real} starts ${real.top - skeleton.top}px from its placeholder`,
          ).toBeLessThanOrEqual(TOLERANCE_PX);
          expect(
            Math.abs(real.bottom - skeleton.bottom),
            `${target.real} ends ${real.bottom - skeleton.bottom}px from its placeholder, so the content under it moves`,
          ).toBeLessThanOrEqual(TOLERANCE_PX);
        });
      }
    }
  }
});
