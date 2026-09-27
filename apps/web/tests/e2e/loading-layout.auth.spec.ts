import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { expect, request, test, type Page } from '@playwright/test';

import { API_BASE, apiToken } from './helpers/api';
import { listPages, WEB_ROOT } from './helpers/list-pages';
import {
  dismissAllHints,
  holdNavigation,
  NAV_TIMEOUT,
  NO_PREFETCH_REASON,
  protectedPages,
} from './helpers/loading-states';

/*
 * A route's loading state must not move the page when the real content replaces it.
 *
 * `PageSkeleton` paints each page's frame while its reads are in flight: the real header, then
 * placeholders standing where the toolbar and the content will be. The defect this pins: at 390px the
 * placeholder toolbar was a single row while the real one stacks the search, each filter and the add
 * button — so /expenses' table landed 88px lower once it loaded, and /dashboard's figures 52px lower
 * because the period picker (stacked under the header on a phone) had no placeholder at all. At
 * 1280px both lined up, which is why nothing had noticed. The investor dashboard's search + picker row
 * was missing the same way (52px at 1280, 96px at 390).
 *
 * The loading state is held on screen by holding the navigation's content (see
 * `helpers/loading-states.ts`); on a dev server, which prefetches no loading state, each test skips
 * itself saying why. CI runs it against the production build.
 *
 * The population, derived: every list page (see `helpers/list-pages.ts`) measured at its toolbar, and
 * every protected page that renders `<DashboardPeriodPicker`, measured at the picker.
 *
 * Two things a loading state cannot know are held out rather than tolerated, both derived from source:
 * a control only some accounts see (the scope pill for a group member, the collections filter once a
 * collection exists — the route is skipped, saying so, when this account has either), and dismissible
 * hints, which reveal themselves with a height animation after the page loads by design (every hint is
 * dismissed first, so the spec measures the layout without them).
 */

const WIDTHS = [390, 1280] as const;
const LOCALES = ['en', 'es'] as const;

// Sub-pixel rounding only. A real mismatch is a whole control's height (32-36px) or more.
const TOLERANCE_PX = 2;
// Motion's `layout` animations settle within ANIMATION_DEFAULT (250ms); measure after they have.
const SETTLE_MS = 600;

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

/*
 * The source of a page and of the `_components` beside it and above it — a list page inside a route
 * group (`accounts/(list)/page.tsx`) keeps its toolbar in the section's `_components`.
 */
function routeSource(target: Target): string {
  const sources = [readFileSync(join(WEB_ROOT, target.file), 'utf8')];
  for (let dir = dirname(target.file); dir.includes('(protected)'); dir = dirname(dir)) {
    const components = join(WEB_ROOT, dir, '_components');
    if (!existsSync(components)) continue;
    for (const name of readdirSync(components).filter((entry) => entry.endsWith('.tsx'))) {
      sources.push(readFileSync(join(components, name), 'utf8'));
    }
  }
  return sources.join('\n');
}

// Which account-dependent controls this route's toolbar can render.
function dependencies(target: Target): AccountDependency[] {
  const source = routeSource(target);
  return [
    ...(source.includes('<ScopePill') ? (['groups'] as const) : []),
    ...(source.includes('<CollectionMultiSelect') ? (['collections'] as const) : []),
  ];
}

const TARGETS: Target[] = [
  ...listPages().map(({ route, file }) => ({
    route,
    file,
    skeleton: '[data-testid="page-skeleton-toolbar"]',
    real: '[data-testid="entity-list-toolbar"]',
  })),
  ...protectedPages()
    .filter(({ file }) =>
      readFileSync(join(WEB_ROOT, file), 'utf8').includes('<DashboardPeriodPicker'),
    )
    .map(({ route, file }) => ({
      route,
      file,
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

async function box(page: Page, selector: string) {
  const found = page.locator(selector).first();
  await expect(found).toBeVisible({ timeout: NAV_TIMEOUT });
  const rect = await found.boundingBox();
  expect(rect, `${selector} has no box`).not.toBeNull();
  return { top: rect!.y, bottom: rect!.y + rect!.height };
}

test.describe('loading states keep the layout (signed in)', () => {
  test.describe.configure({ timeout: 120_000 });

  let state: AccountState;
  test.beforeAll(async () => {
    state = await accountState();
  });

  test('derives the dashboards from the pages that render the period picker', () => {
    // A derivation that found nothing would leave the dashboards untested without failing.
    const routes = TARGETS.filter((target) => target.real.includes('period')).map((t) => t.route);
    expect(routes).toEqual(
      expect.arrayContaining(['/dashboard', '/finance-dashboard', '/investor-dashboard']),
    );
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
          await dismissAllHints(page);
          await page.setViewportSize({ width, height: 900 });

          const measured = await holdNavigation(
            page,
            target.route,
            async () => {
              await page.waitForTimeout(SETTLE_MS);
              return box(page, target.skeleton);
            },
            async () => {
              await page.waitForTimeout(SETTLE_MS);
              return box(page, target.real);
            },
          );
          test.skip(measured === null, NO_PREFETCH_REASON);

          const { held: skeleton, released: real } = measured!;
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

/*
 * Below the dashboards' header: where the first content lands, for a visitor with no currency cookie.
 *
 * That visitor sees each dashboard's "no common currency" warning (the page reads it off the missing
 * cookie), and a loading state that reserved no line for it put the metric cards one warning lower
 * once the page loaded — about 34px on the main and finance dashboards, which measuring only the
 * picker never showed. The spec asserts that the metrics start where the placeholder's content did,
 * and then that the placeholder did reserve the warning — so the case really is the no-cookie visitor.
 *
 * The main dashboard also opens with a first-run welcome for an account that has not finished
 * onboarding — data no loading state can know — so this block marks the account onboarded for its own
 * duration and restores whatever it found.
 */
const DASHBOARDS = TARGETS.filter((target) => target.real.includes('period'));

test.describe('dashboard content stays put under the header (signed in)', () => {
  test.describe.configure({ timeout: 120_000 });

  let onboardedBefore: boolean | null = null;
  const setOnboarded = async (value: boolean) => {
    const token = await apiToken();
    const context = await request.newContext({
      baseURL: API_BASE,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    try {
      const current = await context.get('/settings');
      expect(current.ok(), 'reading settings failed').toBe(true);
      const before = Boolean((await current.json()).onboarding_completed);
      const updated = await context.put('/settings', { data: { onboarding_completed: value } });
      expect(updated.ok(), `updating settings failed with ${updated.status()}`).toBe(true);
      return before;
    } finally {
      await context.dispose();
    }
  };

  test.beforeAll(async () => {
    onboardedBefore = await setOnboarded(true);
  });

  // Never throws: a cleanup raising from `afterAll` would replace the failure that actually happened.
  test.afterAll(async () => {
    if (onboardedBefore === false) {
      await setOnboarded(false).catch((error: Error) =>
        console.warn(`e2e cleanup: restoring onboarding_completed failed (${error.message})`),
      );
    }
  });

  for (const locale of LOCALES) {
    for (const width of WIDTHS) {
      for (const target of DASHBOARDS) {
        test(`${target.route} content at ${width}px in ${locale}`, async ({ page }) => {
          // No currency cookie is set: the visitor this block is about.
          await page
            .context()
            .addCookies([{ name: 'NEXT_LOCALE', value: locale, domain: 'localhost', path: '/' }]);
          await dismissAllHints(page);
          await page.setViewportSize({ width, height: 900 });

          const measured = await holdNavigation(
            page,
            target.route,
            async () => {
              await page.waitForTimeout(SETTLE_MS);
              return {
                content: await box(page, '[data-testid="page-skeleton-dashboard"]'),
                reserved: await page.getByTestId('page-skeleton-notice').isVisible(),
              };
            },
            async () => {
              await page.waitForTimeout(SETTLE_MS);
              return box(page, '[data-testid="dashboard-metrics"]');
            },
          );
          test.skip(measured === null, NO_PREFETCH_REASON);

          const { held, released: real } = measured!;
          expect(
            Math.abs(real.top - held.content.top),
            `the metrics start ${real.top - held.content.top}px from where the loading state's content did`,
          ).toBeLessThanOrEqual(TOLERANCE_PX);
          // And the case really was the no-cookie visitor, whose warning the placeholder reserves.
          expect(held.reserved, 'the loading state reserved no currency warning').toBe(true);
        });
      }
    }
  }
});
