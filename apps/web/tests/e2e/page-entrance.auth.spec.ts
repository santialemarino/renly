import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import {
  expect,
  request,
  test,
  type APIRequestContext,
  type APIResponse,
  type Page,
} from '@playwright/test';

import { ROUTES } from '@/config/routes';
import {
  ANIMATION_DEFAULT,
  PAGE_SKELETON_DELAY_MS,
  PAGE_SKELETON_MIN_VISIBLE_MS,
} from '@/lib/constants/animations';
import { API_BASE, apiToken } from './helpers/api';
import { WEB_ROOT } from './helpers/list-pages';
import {
  dismissAllHints,
  holdNavigation,
  NAV_TIMEOUT,
  NO_PREFETCH_REASON,
  protectedPages,
  START,
} from './helpers/loading-states';

/*
 * How a protected page enters (`PageEntrance` + the `.page-entrance` rules in `globals.css`):
 *
 * - a load that finishes inside `PAGE_SKELETON_DELAY_MS` paints no loading state at all — the page,
 *   header and content together, fades in once, held back by nothing;
 * - a slower one fades the whole loading state in after the delay, keeps it up for at least
 *   `PAGE_SKELETON_MIN_VISIBLE_MS` once it shows, and the page then fades in where it stood — so the
 *   loading state must be the page's exact shape, or the swap moves everything;
 * - a page of the same section served from the router cache (no loading state) still fades in.
 *
 * The geometry half measures every block the real page draws — heading, label, paragraph, field,
 * button, switch, rule — against the same block in its loading state, at both widths and in both
 * locales. The population is derived: every protected page whose loading state draws the page's own
 * sections (`body="page"`) — the integrations page also with API keys, and the localization page also
 * in manual mode, the account data that changes their rows and wrapping — plus one list page and one
 * dashboard, whose bodies are data a loading state
 * cannot know and which are measured at their header here (their toolbar, period picker and first
 * figures are measured by `loading-layout.auth.spec.ts`).
 *
 * The timing half samples the computed opacity of the loading state and of the page on every animation
 * frame (an init script), so what it reads is what was painted.
 *
 * Loading states are held on screen by holding the navigation's content (`helpers/loading-states.ts`);
 * a dev server prefetches none, so each test skips itself there saying why. CI runs the production
 * build.
 */

const WIDTHS = [390, 1280] as const;
const LOCALES = ['en', 'es'] as const;

// Sub-pixel rounding only. A real mismatch is a line of text (16px+) or a field (36px).
const TOLERANCE_PX = 2;
// The entrance's own length, and a margin for the frame that straddles each edge.
const FADE_MS = ANIMATION_DEFAULT * 1000;
const FRAME_MARGIN_MS = 40;
/*
 * How late a CSS animation can start after the frame that mounted its element: a frame or two on a
 * busy machine. Only bounds that a late start could break (shown by now, opaque by now) use it.
 */
const START_LAG_MS = 120;
/*
 * The fast load's answer time. Any answer that is not instant keeps the loading state mounted for
 * React's reveal throttle (~300 ms) whatever it is; an instant one mounts none at all.
 */
const FAST_LOAD_MS = 50;
// Long enough for the delayed fade to finish and the page's own reveals to settle.
const SETTLE_MS = PAGE_SKELETON_DELAY_MS + FADE_MS + 400;

// Everything a page draws that has a box of its own worth comparing.
const BLOCKS = [
  'h1',
  'h2',
  'h3',
  'h4',
  'label',
  'p',
  'input',
  'textarea',
  'button',
  '[role="combobox"]',
  '[role="switch"]',
  '[data-slot="separator"]',
].join(',');

interface Target {
  route: string;
  // Where the navigation starts — any other protected page.
  from: string;
  // `blocks`: every block in `main`; `header`: the page header's title and subtitle only.
  measure: 'blocks' | 'header';
  // Account data the test sets up first, and undoes after.
  account?: AccountSetup;
}

type AccountSetup = 'api-keys' | 'manual-localization';

// How many API keys the populated integrations case seeds — enough rows to wrap and stack.
const SEEDED_API_KEYS = 3;

// The `loading.tsx` beside a page, when it has one.
function loadingSource(pageFile: string): string {
  const file = join(WEB_ROOT, dirname(pageFile), 'loading.tsx');
  return existsSync(file) ? readFileSync(file, 'utf8') : '';
}

const PAGE_BODIES = protectedPages().filter(({ file }) =>
  /\bbody="page"/.test(loadingSource(file)),
);

const TARGETS: Target[] = [
  ...PAGE_BODIES.map(({ route }) => ({
    route,
    from: route === START ? ROUTES.preferences : START,
    measure: 'blocks' as const,
  })),
  { route: ROUTES.integrations, from: START, measure: 'blocks', account: 'api-keys' },
  { route: ROUTES.localization, from: START, measure: 'blocks', account: 'manual-localization' },
  { route: ROUTES.expenses, from: START, measure: 'header' },
  { route: ROUTES.dashboard, from: START, measure: 'header' },
];

interface Box {
  tag: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

// The boxes of what `main` draws, in document order, leaving out what has no box of its own.
async function boxes(page: Page, measure: Target['measure']): Promise<Box[]> {
  return page.evaluate(
    ({ selector, measure }) => {
      const main = document.querySelector('main');
      if (!main) return [];
      const found = [...main.querySelectorAll<HTMLElement>(selector)].filter((element) => {
        if (element.closest('[role="status"], [data-testid="page-entrance-hold"]')) return false;
        const rect = element.getBoundingClientRect();
        return rect.width > 1 && rect.height > 1;
      });
      const picked =
        measure === 'header'
          ? [
              found.find((element) => element.tagName === 'H1'),
              found.find((element) => element.tagName === 'H2'),
            ].filter((element): element is HTMLElement => element !== undefined)
          : found;
      return picked.map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          tag: `${element.tagName.toLowerCase()}${element.getAttribute('role') ? `[${element.getAttribute('role')}]` : ''}`,
          x: rect.x,
          y: rect.y,
          width: rect.width,
          height: rect.height,
        };
      });
    },
    { selector: BLOCKS, measure },
  );
}

// Every block of `real` that does not sit where its placeholder did, described.
function mismatches(skeleton: Box[], real: Box[]): string[] {
  const out: string[] = [];
  real.forEach((box, i) => {
    const held = skeleton[i];
    if (!held) return;
    const off = (['x', 'y', 'width', 'height'] as const).filter(
      (key) => Math.abs(box[key] - held[key]) > TOLERANCE_PX,
    );
    if (held.tag !== box.tag || off.length > 0) {
      out.push(
        `#${i} ${box.tag} at ${off.map((key) => `${key} ${held[key].toFixed(1)}→${box[key].toFixed(1)}`).join(', ') || `(placeholder was ${held.tag})`}`,
      );
    }
  });
  return out;
}

async function api(): Promise<APIRequestContext> {
  return request.newContext({
    baseURL: API_BASE,
    extraHTTPHeaders: { Authorization: `Bearer ${await apiToken()}` },
  });
}

/*
 * Puts the account in the state `setup` names and returns how to put it back. Undoing never throws: a
 * cleanup raising would replace the failure that actually happened.
 */
async function arrange(setup: AccountSetup): Promise<() => Promise<void>> {
  const context = await api();
  if (setup === 'api-keys') {
    const ids: number[] = [];
    for (let i = 0; i < SEEDED_API_KEYS; i += 1) {
      const created = await context.post('/api-keys', { data: { name: `page-entrance ${i + 1}` } });
      expect(created.ok(), `creating an API key failed with ${created.status()}`).toBe(true);
      ids.push(((await created.json()) as { id: number }).id);
    }
    return async () => {
      for (const id of ids) {
        await context.delete(`/api-keys/${id}`).catch(() => undefined);
      }
      await context.dispose();
    };
  }
  const current = await context.get('/settings');
  expect(current.ok(), 'reading settings failed').toBe(true);
  const before = (await current.json()) as {
    timezone: string | null;
    timezone_mode: string | null;
  };
  const updated = await context.put('/settings', {
    data: { timezone: 'Asia/Tokyo', timezone_mode: 'manual' },
  });
  expect(updated.ok(), `updating settings failed with ${updated.status()}`).toBe(true);
  return async () => {
    await context
      .put('/settings', {
        data: { timezone: before.timezone, timezone_mode: before.timezone_mode },
      })
      .catch((error: Error) =>
        console.warn(`e2e cleanup: restoring settings failed (${error.message})`),
      );
    await context.dispose();
  };
}

async function openAt(page: Page, locale: string, width: number) {
  await page
    .context()
    .addCookies([{ name: 'NEXT_LOCALE', value: locale, domain: 'localhost', path: '/' }]);
  await dismissAllHints(page);
  await page.setViewportSize({ width, height: 900 });
}

test.describe('a loading state is the page it stands for (signed in)', () => {
  test.describe.configure({ timeout: 120_000 });

  test('derives the pages whose loading state draws their own sections', () => {
    // A derivation that found nothing would leave the settings pages unmeasured without failing.
    expect(PAGE_BODIES.map(({ route }) => route)).toEqual(
      expect.arrayContaining([
        ROUTES.account,
        ROUTES.alerts,
        ROUTES.localization,
        ROUTES.notifications,
        ROUTES.notificationSettings,
        ROUTES.preferences,
      ]),
    );
  });

  for (const locale of LOCALES) {
    for (const width of WIDTHS) {
      for (const target of TARGETS) {
        const label = target.account ? ` with ${target.account}` : '';
        test(`${target.route}${label} at ${width}px in ${locale}`, async ({ page }) => {
          await openAt(page, locale, width);
          const undo = target.account ? await arrange(target.account) : async () => undefined;

          const measured = await holdNavigation(
            page,
            target.route,
            async () => {
              await page.waitForTimeout(SETTLE_MS);
              return boxes(page, target.measure);
            },
            async () => {
              await page.waitForTimeout(SETTLE_MS);
              await expect(page.locator('main h1').first()).toBeVisible({ timeout: NAV_TIMEOUT });
              return boxes(page, target.measure);
            },
            target.from,
          ).finally(undo);
          test.skip(measured === null, NO_PREFETCH_REASON);

          const { held: skeleton, released: real } = measured!;
          // Not empty: a page that measured nothing would pass any comparison.
          expect(real.length, 'the page drew no blocks to measure').toBeGreaterThan(
            target.measure === 'header' ? 1 : 3,
          );
          expect(
            skeleton.map((box) => box.tag),
            `the loading state draws ${skeleton.length} blocks where the page draws ${real.length}`,
          ).toEqual(real.map((box) => box.tag));
          expect(
            mismatches(skeleton, real),
            'blocks that move when the page replaces its loading state',
          ).toEqual([]);
        });
      }
    }
  }
});

interface Frame {
  t: number;
  // The loading state's computed opacity, or null when none is mounted.
  skeleton: number | null;
  // The page box's (`.page-entrance`) computed opacity, or null when there is none.
  page: number | null;
  // The held copy of a loading state (`PageEntrance`), as painted, or null when there is none.
  hold: number | null;
  path: string;
}

// Records both opacities on every frame, from the first frame of every document the test loads.
async function sampleFrames(page: Page) {
  await page.addInitScript(() => {
    const frames: Frame[] = [];
    (window as unknown as { __entranceFrames: Frame[] }).__entranceFrames = frames;
    const opacity = (element: Element | null) =>
      element ? Number(getComputedStyle(element).opacity) : null;
    const tick = (t: number) => {
      frames.push({
        t,
        skeleton: opacity(document.querySelector('[data-testid="page-skeleton"]')),
        page: opacity(document.querySelector('.page-entrance')),
        hold: document.querySelector('[data-testid="page-skeleton-hold"]')
          ? opacity(document.querySelector('[data-testid="page-entrance-hold"]'))! *
            opacity(document.querySelector('[data-testid="page-skeleton-hold"]'))!
          : null,
        path: location.pathname,
      });
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

async function readFrames(page: Page): Promise<Frame[]> {
  return page.evaluate(() => (window as unknown as { __entranceFrames: Frame[] }).__entranceFrames);
}

/*
 * The held navigation's loading state is the last run of frames with one mounted. Returns the frames
 * of that run, timed from its first, and the frames after it, timed from the run's end.
 */
function split(frames: Frame[]) {
  let end = frames.length - 1;
  while (end >= 0 && frames[end]!.skeleton === null) end -= 1;
  expect(end, 'no loading state was ever mounted').toBeGreaterThanOrEqual(0);
  let start = end;
  while (start > 0 && frames[start - 1]!.skeleton !== null) start -= 1;
  const t0 = frames[start]!.t;
  const t1 = frames[end + 1]?.t ?? frames[end]!.t;
  return {
    during: frames.slice(start, end + 1).map((frame) => ({ ...frame, t: frame.t - t0 })),
    after: frames.slice(end + 1).map((frame) => ({ ...frame, t: frame.t - t1 })),
  };
}

const ROUTE = ROUTES.preferences;

test.describe('the page entrance (signed in)', () => {
  test.describe.configure({ timeout: 120_000 });

  test.beforeEach(async ({ page }) => {
    await openAt(page, 'en', 1280);
    await sampleFrames(page);
  });

  test('a fast load paints no loading state, and the page fades in whole', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    /*
     * A fast load, made deterministic: the first navigation records the server's answer, and the
     * second, from the same page, gets it back after `FAST_LOAD_MS` — so what is measured is the
     * entrance, not how long this server takes to render the page.
     */
    let recorded: APIResponse | null = null;
    await page.route(
      (url) => url.pathname === ROUTE,
      async (route) => {
        const headers = route.request().headers();
        if (headers['rsc'] !== '1' || headers['next-router-prefetch']) return route.continue();
        if (recorded) {
          await new Promise((resolve) => setTimeout(resolve, FAST_LOAD_MS));
          return route.fulfill({ response: recorded });
        }
        recorded = await route.fetch();
        return route.fulfill({ response: recorded });
      },
    );
    const navigate = async () => {
      await page.goto(START);
      await expect(page.locator('main h1').first()).toBeVisible({ timeout: NAV_TIMEOUT });
      await page.evaluate((target) => {
        const router = (window as unknown as { next: { router: { prefetch(r: string): void } } })
          .next.router;
        router.prefetch(target);
      }, ROUTE);
      await page.waitForLoadState('networkidle');
      await page.evaluate((target) => {
        (window as unknown as { next: { router: { push(r: string): void } } }).next.router.push(
          target,
        );
      }, ROUTE);
      await expect(page).toHaveURL(new RegExp(`${ROUTE}$`), { timeout: NAV_TIMEOUT });
      await expect(page.getByTestId('page-skeleton')).toHaveCount(0, { timeout: NAV_TIMEOUT });
      await page.waitForTimeout(SETTLE_MS);
    };
    await navigate();
    expect(recorded, 'the navigation made no request to record').not.toBeNull();
    await navigate();

    const frames = await readFrames(page);
    const arrived = frames.findIndex((frame) => frame.path === ROUTE);
    expect(arrived, 'never saw the navigation').toBeGreaterThan(0);
    const after = frames.slice(arrived);
    // It was there — mounted and tracked — for less than the delay, and never painted.
    const mounted = after.filter((frame) => frame.skeleton !== null);
    expect(
      mounted.length,
      'the loading state never mounted, so this is not the case under test',
    ).toBeGreaterThan(0);
    expect(
      mounted.at(-1)!.t - mounted[0]!.t,
      'a fast answer took longer than the delay to replace the loading state here, so no fast load could be produced',
    ).toBeLessThan(PAGE_SKELETON_DELAY_MS);
    expect(
      Math.max(...after.map((frame) => frame.skeleton ?? 0)),
      'the loading state was painted',
    ).toBe(0);
    expect(
      after.filter((frame) => frame.hold !== null),
      'a loading state nobody saw was held',
    ).toEqual([]);
    // The whole page box — header included — fades in, and nothing holds it back once it is there.
    const shown = after.filter((frame) => frame.skeleton === null);
    expect(Math.min(...shown.map((frame) => frame.page!)), 'the page did not fade in').toBeLessThan(
      0.5,
    );
    const start = shown.find((frame) => frame.page! < 1)!.t;
    const opaque = shown.find((frame) => frame.t > start && frame.page === 1);
    expect(opaque?.t, 'the page never became opaque').toBeDefined();
    const hidden = shown.filter(
      (frame) => frame.page! <= 0.01 && frame.t > start + 2 * FRAME_MARGIN_MS,
    );
    expect(
      hidden.map((frame) => Math.round(frame.t - start)),
      'the page was held back after its content arrived',
    ).toEqual([]);
  });

  test('a loading state that has just shown stays up for the minimum, then crossfades', async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    // Released just after the loading state starts to show: a load landing just past the delay.
    const measured = await holdNavigation(
      page,
      ROUTE,
      async () => {
        await page.waitForFunction(() => {
          const skeleton = document.querySelector('[data-testid="page-skeleton"]');
          return skeleton !== null && Number(getComputedStyle(skeleton).opacity) > 0;
        });
        await page.waitForTimeout(FRAME_MARGIN_MS);
      },
      async () => {
        await page.waitForTimeout(PAGE_SKELETON_MIN_VISIBLE_MS + SETTLE_MS);
        return readFrames(page);
      },
    );
    test.skip(measured === null, NO_PREFETCH_REASON);

    const frames = measured!.released;
    let end = frames.length - 1;
    while (end >= 0 && frames[end]!.skeleton === null) end -= 1;
    let start = end;
    while (start > 0 && frames[start - 1]!.skeleton !== null) start -= 1;
    const shownAt = frames.slice(start, end + 1).find((frame) => frame.skeleton! > 0)?.t;
    expect(shownAt, 'the loading state never showed').toBeDefined();
    const goneAt = frames[end + 1]!.t;
    // The case under test: the content arrived well before the minimum was up.
    expect(goneAt - shownAt!).toBeLessThan(PAGE_SKELETON_MIN_VISIBLE_MS - 2 * FRAME_MARGIN_MS);

    const after = frames.slice(end + 1);
    const pageShows = after.find((frame) => frame.page !== null && frame.page > 0.01);
    expect(pageShows, 'the page never appeared').toBeDefined();
    expect(
      pageShows!.t - shownAt!,
      'the page replaced its loading state before the minimum was up',
    ).toBeGreaterThanOrEqual(PAGE_SKELETON_MIN_VISIBLE_MS - FRAME_MARGIN_MS);
    // Until then the loading state is still what is painted, not an empty column.
    const gap = after.filter((frame) => frame.t < pageShows!.t);
    expect(gap.length).toBeGreaterThan(0);
    expect(
      gap.filter((frame) => frame.hold === null || frame.hold === 0),
      'frames where neither the loading state nor the page was painted',
    ).toEqual([]);
    expect(after.at(-1)?.page).toBe(1);
    expect(after.at(-1)?.hold, 'the held copy was never removed').toBeNull();
  });

  test('a slow load fades the loading state in after the delay, then the page in', async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    const measured = await holdNavigation(
      page,
      ROUTE,
      async () => {
        await page.waitForTimeout(SETTLE_MS);
      },
      async () => {
        await page.waitForTimeout(SETTLE_MS);
        return readFrames(page);
      },
    );
    test.skip(measured === null, NO_PREFETCH_REASON);

    const { during, after } = split(measured!.released);
    const early = during.filter((frame) => frame.t < PAGE_SKELETON_DELAY_MS - FRAME_MARGIN_MS);
    const fading = during.filter((frame) => frame.skeleton! > 0.05 && frame.skeleton! < 0.95);
    const late = during.filter(
      (frame) => frame.t > PAGE_SKELETON_DELAY_MS + FADE_MS + START_LAG_MS,
    );
    expect(Math.max(...early.map((frame) => frame.skeleton!))).toBe(0);
    expect(fading.length, 'the loading state appeared without fading in').toBeGreaterThan(0);
    expect(late.length).toBeGreaterThan(0);
    expect(
      Math.min(...late.map((frame) => frame.skeleton!)),
      'the loading state never showed',
    ).toBe(1);
    const first = after.find((frame) => frame.page !== null);
    expect(first?.page, 'the page replaced its loading state without fading in').toBeLessThan(0.5);
    expect(after.at(-1)?.page).toBe(1);
    // Shown for longer than the minimum: nothing to hold.
    expect(after.filter((frame) => frame.hold !== null)).toEqual([]);
  });

  test('during the hold, a click on a placeholder reaches nothing on the page beneath', async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    const measured = await holdNavigation(
      page,
      ROUTE,
      async () => {
        await page.waitForFunction(() => {
          const skeleton = document.querySelector('[data-testid="page-skeleton"]');
          return skeleton !== null && Number(getComputedStyle(skeleton).opacity) > 0;
        });
        // A placeholder that stands where a real control will: the first currency field.
        return page
          .locator('[data-testid="page-skeleton-ghost"] [role="combobox"]')
          .first()
          .boundingBox();
      },
      async () => {
        const hold = page.getByTestId('page-skeleton-hold');
        await expect(hold, 'no hold started, so this is not the case under test').toHaveCount(1);
        return page;
      },
    );
    test.skip(measured === null, NO_PREFETCH_REASON);

    const target = measured!.held;
    expect(target, 'the loading state drew no combobox placeholder').not.toBeNull();
    await page.mouse.click(target!.x + target!.width / 2, target!.y + target!.height / 2);
    expect(
      await page.getByTestId('page-skeleton-hold').count(),
      'the hold was over before the click landed, so the click proved nothing',
    ).toBe(1);

    await page.waitForTimeout(SETTLE_MS);
    await expect(
      page.locator('[data-radix-popper-content-wrapper]'),
      'a click on the held placeholder opened the real control beneath it',
    ).toHaveCount(0);
    const focused = await page.evaluate(() =>
      document.activeElement?.closest('.page-entrance [role="combobox"], .page-entrance input')
        ? document.activeElement.outerHTML.slice(0, 120)
        : null,
    );
    expect(focused, 'a control of the transparent page took focus').toBeNull();
  });

  test('a page of the same section served from the router cache still fades in', async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    const context = await api();
    const settings = (await (await context.get('/settings')).json()) as {
      primary_currency: string | null;
    };
    const created = await context.post('/accounts', {
      data: {
        name: `page-entrance ${Date.now()}`,
        type: 'bank',
        currency: settings.primary_currency ?? 'ARS',
        opening_balance: '0.00',
        opening_date: new Date().toISOString().slice(0, 10),
      },
    });
    expect(created.ok(), `creating an account failed with ${created.status()}`).toBe(true);
    const { id, name } = (await created.json()) as { id: number; name: string };
    try {
      await page.goto(ROUTES.accounts);
      await expect(page.locator('main h1').first()).toBeVisible({ timeout: NAV_TIMEOUT });
      const detail = `${ROUTES.accounts}/${id}`;
      await page.evaluate((target) => {
        (window as unknown as { next: { router: { push(r: string): void } } }).next.router.push(
          target,
        );
      }, detail);
      await expect(page.locator('main h1').first()).toHaveText(name, { timeout: NAV_TIMEOUT });
      await page.waitForTimeout(SETTLE_MS);

      // Back to the list: the same template, and the list comes from the router cache.
      await page.goBack();
      await expect(page.locator('main h1').first()).not.toHaveText(name, { timeout: NAV_TIMEOUT });
      await page.waitForTimeout(SETTLE_MS);

      const frames = await readFrames(page);
      const leftDetail = frames.findIndex(
        (frame, i) => i > 0 && frames[i - 1]!.path === detail && frame.path === ROUTES.accounts,
      );
      expect(leftDetail, 'never saw the navigation back to the list').toBeGreaterThan(0);
      const back = frames.slice(leftDetail);
      expect(
        back.filter((frame) => frame.skeleton !== null),
        'the list showed a loading state, so this is not the cached case',
      ).toEqual([]);
      const firstFrames = back.filter((frame) => frame.t - back[0]!.t <= 4 * FRAME_MARGIN_MS);
      expect(
        Math.min(...firstFrames.map((frame) => frame.page!)),
        'the cached page swapped in without fading',
      ).toBeLessThan(0.5);
      expect(back.at(-1)?.page).toBe(1);
    } finally {
      await context.delete(`/accounts/${id}`).catch(() => undefined);
      await context.dispose();
    }
  });

  test('under reduced motion nothing fades: the loading state appears at once after the delay, the page at once', async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    try {
      const measured = await holdNavigation(
        page,
        ROUTE,
        async () => {
          await page.waitForTimeout(SETTLE_MS);
        },
        async () => {
          await page.waitForTimeout(SETTLE_MS);
          return readFrames(page);
        },
      );
      test.skip(measured === null, NO_PREFETCH_REASON);

      const { during, after } = split(measured!.released);
      const early = during.filter((frame) => frame.t < PAGE_SKELETON_DELAY_MS - FRAME_MARGIN_MS);
      const shown = during.filter((frame) => frame.t > PAGE_SKELETON_DELAY_MS + START_LAG_MS);
      // The delay still decides whether it shows; only the fade goes.
      expect(Math.max(...early.map((frame) => frame.skeleton!))).toBe(0);
      expect(shown.length).toBeGreaterThan(0);
      expect(
        Math.min(...shown.map((frame) => frame.skeleton!)),
        'the loading state faded in under reduced motion',
      ).toBe(1);
      const pageFrames = after.filter((frame) => frame.page !== null);
      expect(pageFrames.length).toBeGreaterThan(0);
      expect(
        Math.min(...pageFrames.map((frame) => frame.page!)),
        'the page faded in under reduced motion',
      ).toBe(1);
    } finally {
      await page.emulateMedia({ reducedMotion: 'no-preference' });
    }
  });
});
