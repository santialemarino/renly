import { expect, test, type CDPSession, type Page } from '@playwright/test';

import { createExpenseViaQuickAdd, deleteExpenseByMarker, testMarker } from './helpers/factories';

/*
 * `prefers-reduced-motion: reduce`, measured in the only place it exists: a real browser's computed
 * style. Two mechanisms carry it and each is invisible to every other kind of test.
 *
 * - The overlay primitives' open/close are tw-animate-css `enter` / `exit` keyframes, and one
 *   unlayered `@media` block in `@repo/ui`'s stylesheet resets the variables those keyframes read
 *   into a transform. Nothing about a component changes, so only the computed transform can show it.
 * - motion/react animations follow a root `MotionConfig reducedMotion="user"`. Remove it and every
 *   call site still renders and animates — just with the full movement under `reduce`.
 *
 * Every assertion has a twin WITHOUT `reduce` that requires the movement to be there, so a check
 * that could never see a transform (a wrong selector, an animation that finished before sampling)
 * fails instead of passing.
 */

// Deliberately not the dashboard, which auto-starts the welcome tour on an un-onboarded account.
const START = '/snapshots';
const EXPENSES = '/expenses';
const INVESTMENTS = '/investments';
const PHONE = { width: 390, height: 844 };
const DESKTOP = { width: 1280, height: 900 };
const COOKIE_KEY = 'cookie-consent-dismissed';

/*
 * How long to wait for a surface's animation to start, and for a whole test. Read the way
 * playwright.config.ts reads CI (`CI=false` / `CI=0` opt out).
 *
 * Locally the spec runs against a dev server, where a first compile of the route plus the quick-add's
 * first open can pass 30s, so both budgets are long. CI serves a production build — nothing compiles
 * on demand — so there the budgets are short: a regression that stops every enter animation fails
 * each test in about 20s instead of running each one to its full local budget, which across retries
 * would push the job past its timeout and cancel the report and trace uploads with it.
 */
// eslint-disable-next-line turbo/no-undeclared-env-vars
const ciEnv = process.env.CI;
const isCI = !!ciEnv && ciEnv !== 'false' && ciEnv !== '0';
const FRAME_POLL_MS = isCI ? 20_000 : 60_000;
// A navigation plus up to two frame polls (enter, exit), with room for the tooltip's seeded row.
const TEST_BUDGET_MS = isCI ? 90_000 : 180_000;

// One painted frame of the cookie banner: its vertical offset and how opaque it was.
interface BannerFrame {
  y: number;
  opacity: number;
}

// The investment dialog's Ticker field reveal, and one painted frame of it.
const TICKER_REVEAL = 'investment-ticker-reveal';
interface RevealFrame {
  margin: number;
  opacity: number;
}

/*
 * The document timeline is FROZEN while a primitive opens, so its `enter` animation sits at its first
 * frame for as long as the test needs, and its `exit` holds the element mounted until released. A
 * sample taken by racing a 150-500ms animation against the test runner would pass or fail on machine
 * load; this one reads the exact frame asked for.
 */
async function freezeAnimations(page: Page): Promise<CDPSession> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Animation.enable');
  await cdp.send('Animation.setPlaybackRate', { playbackRate: 0 });
  return cdp;
}

async function releaseAnimations(cdp: CDPSession) {
  await cdp.send('Animation.setPlaybackRate', { playbackRate: 1 });
}

interface Frame {
  identity: boolean;
  scale: number;
  translateX: number;
  translateY: number;
  opacity: number;
}

/*
 * The element's computed transform and opacity at `progress` (0-1) through its running `enter` or
 * `exit` keyframes, or null while that animation is not running on it yet. The Radix popper wrapper
 * positions the content with a transform of its own, so the element sampled is always the one that
 * carries the animation, never an ancestor.
 */
async function frameAt(
  page: Page,
  selector: string,
  keyframes: 'enter' | 'exit',
  progress: number,
): Promise<Frame | null> {
  return page.evaluate(
    ([sel, name, at]) => {
      const el = document.querySelector(sel as string);
      const animation = el
        ?.getAnimations()
        .find((a) => (a as CSSAnimation).animationName === name) as CSSAnimation | undefined;
      if (!el || !animation?.effect) {
        return null;
      }
      const duration = Number(animation.effect.getComputedTiming().duration);
      animation.currentTime = duration * (at as number);
      const style = getComputedStyle(el);
      const matrix = new DOMMatrixReadOnly(
        style.transform === 'none' ? undefined : style.transform,
      );
      return {
        identity: matrix.isIdentity,
        scale: matrix.a,
        translateX: matrix.e,
        translateY: matrix.f,
        opacity: Number(style.opacity),
      };
    },
    [selector, keyframes, progress] as const,
  );
}

async function waitForFrame(
  page: Page,
  selector: string,
  keyframes: 'enter' | 'exit',
  progress: number,
): Promise<Frame> {
  let frame: Frame | null = null;
  await expect
    .poll(
      async () => {
        frame = await frameAt(page, selector, keyframes, progress);
        return frame !== null;
      },
      // The animation cannot start before the surface mounts; see FRAME_POLL_MS.
      { timeout: FRAME_POLL_MS, message: `no running "${keyframes}" animation on ${selector}` },
    )
    .toBe(true);
  return frame as unknown as Frame;
}

interface Surface {
  name: string;
  // The element that carries the enter/exit animation.
  content: string;
  viewport: { width: number; height: number };
  // Navigates to where the surface lives, before the timeline is frozen.
  prepare: (page: Page) => Promise<void>;
  open: (page: Page) => Promise<void>;
  close: (page: Page) => Promise<void>;
}

const pressEscape = (page: Page) => page.keyboard.press('Escape');

const DIALOG: Surface = {
  name: 'dialog',
  content: '[data-slot="dialog-content"]',
  viewport: DESKTOP,
  prepare: async (page) => {
    await page.goto(START);
    await expect(page.getByTestId('quick-add-trigger')).toBeVisible();
  },
  open: (page) => page.getByTestId('quick-add-trigger').click(),
  close: pressEscape,
};

const POPOVER: Surface = {
  name: 'popover',
  content: '[data-slot="popover-content"]',
  viewport: DESKTOP,
  prepare: async (page) => {
    await page.goto(START);
    await expect(page.getByTestId('notification-bell')).toBeVisible();
  },
  open: (page) => page.getByTestId('notification-bell').click(),
  close: pressEscape,
};

// The mobile navigation: below the breakpoint the sidebar is a Sheet, the one primitive that slides.
const SHEET: Surface = {
  name: 'mobile sheet',
  content: '[data-sidebar="sidebar"][data-mobile="true"]',
  viewport: PHONE,
  prepare: async (page) => {
    await page.goto(START);
    await expect(page.locator('[data-sidebar="trigger"]')).toBeVisible();
  },
  open: (page) => page.locator('[data-sidebar="trigger"]').click(),
  close: pressEscape,
};

// A row action's tooltip; the row is one expense the test writes and removes itself.
function tooltipSurface(): Surface {
  return {
    name: 'tooltip',
    content: '[data-slot="tooltip-content"]',
    viewport: DESKTOP,
    prepare: async (page) => {
      await page.goto(EXPENSES);
      await expect(page.getByTestId('expense-delete').first()).toBeVisible({ timeout: 20_000 });
    },
    open: (page) => page.getByTestId('expense-delete').first().hover(),
    close: pressEscape,
  };
}

/*
 * Opens and closes one surface on a frozen timeline, returning its first entrance frame and the
 * frame halfway through its exit — and proving the close still completes once time runs again,
 * since Radix Presence unmounts a closing primitive only when its animation ENDS.
 */
async function openAndClose(page: Page, surface: Surface) {
  await page.setViewportSize(surface.viewport);
  await surface.prepare(page);
  const cdp = await freezeAnimations(page);
  try {
    await surface.open(page);
    const enter = await waitForFrame(page, surface.content, 'enter', 0);
    await releaseAnimations(cdp);
    await expect(page.locator(surface.content)).toBeVisible();

    await cdp.send('Animation.setPlaybackRate', { playbackRate: 0 });
    await surface.close(page);
    const exit = await waitForFrame(page, surface.content, 'exit', 0.5);
    await releaseAnimations(cdp);
    await expect(page.locator(surface.content)).toHaveCount(0);
    return { enter, exit };
  } finally {
    await releaseAnimations(cdp);
  }
}

// The zoom / slide the primitive has with motion allowed: the check below can see a transform.
function expectMoves(frame: Frame) {
  expect(frame.identity, JSON.stringify(frame)).toBe(false);
}

// Under reduce: no scale, no translate — and the opacity is mid-fade, so there is still feedback.
function expectFadesOnly(frame: Frame, expectedOpacity: 'start' | 'mid') {
  expect(frame.identity, JSON.stringify(frame)).toBe(true);
  if (expectedOpacity === 'start') {
    expect(frame.opacity).toBe(0);
  } else {
    expect(frame.opacity).toBeGreaterThan(0);
    expect(frame.opacity).toBeLessThan(1);
  }
}

async function checkSurface(page: Page, surface: Surface, reduced: boolean) {
  await page.emulateMedia({ reducedMotion: reduced ? 'reduce' : 'no-preference' });
  const { enter, exit } = await openAndClose(page, surface);
  if (reduced) {
    expectFadesOnly(enter, 'start');
    expectFadesOnly(exit, 'mid');
  } else {
    expectMoves(enter);
    expectMoves(exit);
  }
}

test.describe('reduced motion (signed in)', () => {
  // See FRAME_POLL_MS / TEST_BUDGET_MS. A warm run takes seconds either way.
  test.setTimeout(TEST_BUDGET_MS);

  for (const surface of [DIALOG, POPOVER, SHEET]) {
    for (const reduced of [true, false]) {
      test(`${surface.name} ${reduced ? 'only fades under reduce' : 'zooms or slides without reduce'}`, async ({
        page,
      }) => {
        await checkSurface(page, surface, reduced);
      });
    }
  }

  test('a tooltip only fades under reduce, and zooms without it', async ({ page }) => {
    const marker = testMarker('reduced-motion-tooltip');
    try {
      await page.goto(START);
      await createExpenseViaQuickAdd(page, marker, '12.34');
      await checkSurface(page, tooltipSurface(), true);
      await checkSurface(page, tooltipSurface(), false);
    } finally {
      await page.emulateMedia({ reducedMotion: 'no-preference' });
      await page.goto(EXPENSES);
      await deleteExpenseByMarker(page, marker);
    }
  });

  for (const reduced of [true, false]) {
    test(`the cookie banner ${reduced ? 'does not move under reduce' : 'rises without reduce'}`, async ({
      page,
    }) => {
      /*
       * motion/react, not CSS: the banner animates `y` from 24px and opacity from 0. Its `y` runs on
       * motion's own frame loop rather than on the document timeline, so it is sampled on every frame
       * from the banner's first paint instead of frozen.
       *
       * What the reader must never SEE is the banner displaced. The very first frame always renders
       * motion's `initial` (24px down, fully transparent) before an instant reduced-motion jump lands,
       * so the assertion is on displacement while visible, not on the transform alone: under reduce no
       * frame may be both off its resting place and at all opaque; without it some frame must be, or
       * the sampler saw nothing.
       */
      await page.addInitScript((key) => {
        localStorage.removeItem(key);
        const samples: BannerFrame[] = [];
        (window as unknown as { __banner: BannerFrame[] }).__banner = samples;
        /*
         * Read AFTER each frame is painted, not inside requestAnimationFrame: this script's rAF
         * callback is queued before motion's, so reading there sees the value motion is about to
         * replace in that same frame — one that never reaches the screen. A message posted from rAF is
         * delivered after the frame renders, so it reads what the frame actually showed.
         */
        const channel = new MessageChannel();
        channel.port1.onmessage = () => {
          const el = document.querySelector('[data-testid="cookie-consent"]');
          if (el) {
            const style = getComputedStyle(el);
            const t = style.transform;
            samples.push({
              y: new DOMMatrixReadOnly(t === 'none' ? undefined : t).f,
              opacity: Number(style.opacity),
            });
          }
          if (samples.length < 60) {
            requestAnimationFrame(tick);
          }
        };
        const tick = () => channel.port2.postMessage(null);
        requestAnimationFrame(tick);
      }, COOKIE_KEY);
      await page.emulateMedia({ reducedMotion: reduced ? 'reduce' : 'no-preference' });
      await page.goto(START);
      await expect(page.getByTestId('cookie-consent')).toBeVisible();
      await expect
        .poll(() =>
          page.evaluate(() => (window as unknown as { __banner: BannerFrame[] }).__banner.length),
        )
        .toBe(60);

      const samples = await page.evaluate(
        () => (window as unknown as { __banner: BannerFrame[] }).__banner,
      );
      const seenDisplaced = samples.filter((frame) => frame.y !== 0 && frame.opacity > 0);
      /*
       * And it must actually ARRIVE: a banner that never became visible is never seen displaced
       * either, so without this the reduce case passes on a banner stuck transparent. Sixty frames is
       * about a second, well past its ANIMATION_DEFAULT fade.
       */
      expect(
        samples.some((frame) => frame.y === 0 && frame.opacity === 1),
        JSON.stringify(samples.at(-1)),
      ).toBe(true);
      if (reduced) {
        expect(seenDisplaced).toEqual([]);
      } else {
        expect(seenDisplaced.length).toBeGreaterThan(0);
      }
    });
  }

  for (const reduced of [true, false]) {
    test(`the investment ticker reveal ${reduced ? 'does not slide under reduce' : 'slides without reduce'}`, async ({
      page,
    }) => {
      /*
       * The one kind of motion MotionConfig does NOT reduce: margin and padding are not positional
       * values, so under `reduce` motion still tweens them. The Ticker field reveals beside Broker
       * with `marginRight: -12 → 0` (absorbing the flex gap), and without its own per-value gate it
       * slides 12px sideways while the rest of the reveal is instant. Sampled on every painted frame
       * after picking a category that has a ticker, the same way as the banner.
       */
      await page.setViewportSize(DESKTOP);
      await page.emulateMedia({ reducedMotion: reduced ? 'reduce' : 'no-preference' });
      await page.goto(INVESTMENTS);
      await page.getByTestId('entity-list-add').click();
      const dialog = page.locator('[data-slot="dialog-content"]');
      await expect(dialog).toBeVisible({ timeout: FRAME_POLL_MS });
      // The category picker is the dialog's first combobox; no ticker field exists until one is chosen.
      await dialog.getByRole('combobox').first().click();
      await expect(page.getByTestId(TICKER_REVEAL)).toHaveCount(0);

      await page.evaluate((testId) => {
        const samples: RevealFrame[] = [];
        (window as unknown as { __reveal: RevealFrame[] }).__reveal = samples;
        let frames = 0;
        // Read after each frame paints — see the banner sampler above for why not inside rAF.
        const channel = new MessageChannel();
        channel.port1.onmessage = () => {
          frames += 1;
          const el = document.querySelector(`[data-testid="${testId}"]`);
          if (el) {
            const style = getComputedStyle(el);
            samples.push({ margin: parseFloat(style.marginRight), opacity: Number(style.opacity) });
          }
          if (frames < 60) {
            requestAnimationFrame(tick);
          }
        };
        const tick = () => channel.port2.postMessage(null);
        requestAnimationFrame(tick);
      }, TICKER_REVEAL);
      await page.getByRole('option', { name: /cedears/i }).click();
      await expect(page.getByTestId(TICKER_REVEAL)).toBeVisible();
      await expect
        .poll(() =>
          page.evaluate(() => (window as unknown as { __reveal: RevealFrame[] }).__reveal.length),
        )
        .toBeGreaterThan(30);

      const samples = await page.evaluate(
        () => (window as unknown as { __reveal: RevealFrame[] }).__reveal,
      );
      // It must arrive either way, or "never seen sliding" would pass on a field that never showed.
      expect(
        samples.some((frame) => frame.margin === 0 && frame.opacity === 1),
        JSON.stringify(samples.at(-1)),
      ).toBe(true);
      const seenSliding = samples.filter((frame) => frame.margin !== 0 && frame.opacity > 0);
      if (reduced) {
        expect(seenSliding).toEqual([]);
      } else {
        expect(seenSliding.length).toBeGreaterThan(0);
      }
    });
  }
});
