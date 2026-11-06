import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { expect, test, type Page } from '@playwright/test';

import { ROUTES } from '@/config/routes';
import { ANIMATION_DEFAULT, PAGE_SKELETON_DELAY_MS } from '@/lib/constants/animations';
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
 * How a protected page enters (`app/(protected)/template.tsx` + the `.page-entrance` rules in
 * `globals.css`):
 *
 * - a load that finishes inside `PAGE_SKELETON_DELAY_MS` paints no loading state at all — the page,
 *   header and content together, fades in once;
 * - a slower one fades the whole loading state in after the delay, and the page then fades in where it
 *   stood — so the loading state must be the page's exact shape, or the swap moves everything.
 *
 * The geometry half measures every block the real page draws — heading, label, paragraph, field,
 * button, switch, rule — against the same block in its loading state, at both widths and in both
 * locales. The population is derived: every protected page whose loading state draws the page's own
 * sections (`body="page"`), plus one list page and one dashboard, whose bodies are data a loading state
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
}

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
        if (element.closest('[role="status"]')) return false;
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
        ROUTES.preferences,
      ]),
    );
  });

  for (const locale of LOCALES) {
    for (const width of WIDTHS) {
      for (const target of TARGETS) {
        test(`${target.route} at ${width}px in ${locale}`, async ({ page }) => {
          await openAt(page, locale, width);

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
          );
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
    // Released the moment the loading state mounts: the fastest load a navigation can have.
    const measured = await holdNavigation(
      page,
      ROUTE,
      async () => undefined,
      async () => {
        await page.waitForTimeout(SETTLE_MS);
        return readFrames(page);
      },
    );
    test.skip(measured === null, NO_PREFETCH_REASON);

    const { during, after } = split(measured!.released);
    const early = during.filter((frame) => frame.t < PAGE_SKELETON_DELAY_MS - FRAME_MARGIN_MS);
    expect(early.length, 'no frame was sampled inside the delay').toBeGreaterThan(0);
    expect(
      Math.max(...early.map((frame) => frame.skeleton!)),
      'the loading state was painted inside the delay',
    ).toBe(0);
    // The whole page box — header included — starts from transparent and ends opaque.
    const first = after.find((frame) => frame.page !== null);
    expect(
      first?.page,
      'the page did not fade in (its first frame was already opaque)',
    ).toBeLessThan(0.5);
    expect(after.at(-1)?.page).toBe(1);
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
      (frame) => frame.t > PAGE_SKELETON_DELAY_MS + FADE_MS + FRAME_MARGIN_MS,
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
      const shown = during.filter((frame) => frame.t > PAGE_SKELETON_DELAY_MS + FRAME_MARGIN_MS);
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
