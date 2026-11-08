import { expect, test, type Page } from '@playwright/test';

import { ROUTES } from '@/config/routes';
import { NAVIGATION_PENDING_DELAY_MS } from '@/lib/constants/animations';
import { waitForHydration } from './helpers/hydration';
import {
  delayNavigationTo,
  dismissAllHints,
  holdNavigationTo,
  markClick,
  NAV_TIMEOUT,
  openNavGroups,
  openPage,
  PROGRESS_BAR,
  sidebarLink,
  startSampling,
  stopSampling,
  swapIndex,
  type Frame,
} from './helpers/navigation';

/*
 * The feedback a navigation gives while the old page is still on screen.
 *
 * - The destination's nav item is active from the click itself, not from the swap.
 * - Past `NAVIGATION_PENDING_DELAY_MS`, and only then, a progress bar across the top of the main column
 *   and — for a change of page — the old page dimmed, `aria-busy` and taking no pointer input; the sidebar stays usable,
 *   so another click takes over. Both are gone in the frame the new page arrives.
 * - A navigation faster than the delay shows neither.
 *
 * "Slow" is made, not hoped for: the navigation's own request is held back in the browser, so the bar
 * has to appear and the wait cannot end early on a fast machine. The frames are sampled every animation
 * frame from the click (`helpers/navigation.ts`). The first test holds the request until the bar has
 * been seen rather than for a fixed time, and reads the bar's first frame from the samples rather than
 * expecting it by a fixed moment: a timer only promises not to fire EARLY, and on a loaded runner it
 * paints well after the delay.
 */

const ORIGIN = ROUTES.alerts;
const TARGET = ROUTES.income;
const OTHER = ROUTES.expenses;
const HELD_MS = 600;
// How long the first test keeps the navigation held once the bar is on screen.
const HELD_AFTER_BAR_MS = 300;

// The frames in [from, to) ms after the click.
function between(frames: Frame[], from: number, to: number) {
  return frames.filter((frame) => frame.t >= from && frame.t < to);
}

async function openOrigin(page: Page) {
  await dismissAllHints(page);
  await openPage(page, ORIGIN);
  await openNavGroups(page);
  await waitForHydration(sidebarLink(page, TARGET));
}

test.describe('navigation feedback', () => {
  test.setTimeout(60_000);
  test.use({ viewport: { width: 1280, height: 900 } });

  test('a slow navigation: active on the click, bar and dim only past the delay, gone on the swap', async ({
    page,
  }) => {
    await openOrigin(page);
    const release = await holdNavigationTo(page, TARGET);
    try {
      await startSampling(page);
      await markClick(page);
      await sidebarLink(page, TARGET).click();
      await expect(page.getByTestId(PROGRESS_BAR)).toBeVisible();
      // The page is busy and takes no pointer input; the sidebar still does.
      const main = page.locator('main');
      await expect(main).toHaveAttribute('aria-busy', 'true');
      expect(await main.evaluate((element) => getComputedStyle(element).pointerEvents)).toBe(
        'none',
      );
      expect(
        Number(await main.evaluate((element) => getComputedStyle(element).opacity)),
      ).toBeLessThan(1);
      await expect(sidebarLink(page, OTHER)).toBeEnabled();
      // A few more frames of the busy page before it is let through.
      await page.waitForTimeout(HELD_AFTER_BAR_MS);
    } finally {
      release();
    }
    await expect(page).toHaveURL(new RegExp(`${TARGET}$`), { timeout: NAV_TIMEOUT });
    await expect(page.locator('main h1').first()).toBeVisible();
    await page.waitForTimeout(200);
    const { frames } = await stopSampling(page);

    const swap = swapIndex(frames);
    expect(swap).toBeGreaterThan(0);
    const swapAt = frames[swap]!.t;

    // The destination is active from the first frames after the click, and the origin no longer is.
    const first = frames.find((frame) => frame.active.includes(TARGET));
    expect(first, 'the clicked item never turned active before the swap').toBeDefined();
    expect(first!.t).toBeLessThan(NAVIGATION_PENDING_DELAY_MS);
    expect(first!.active).not.toContain(ORIGIN);
    for (const frame of between(frames, first!.t, swapAt)) {
      expect(frame.active, `at ${Math.round(frame.t)} ms`).toEqual([TARGET]);
    }

    // Nothing before the delay.
    const early = between(frames, 0, NAVIGATION_PENDING_DELAY_MS);
    expect(early.length).toBeGreaterThan(0);
    expect(early.filter((frame) => frame.bar || frame.busy)).toEqual([]);
    // Bar and dim arrive together, past the delay, and hold in every frame until the swap.
    const shown = frames.findIndex((frame) => frame.bar || frame.busy);
    expect(shown, 'the bar never showed before the swap').toBeGreaterThan(0);
    expect(shown).toBeLessThan(swap);
    expect(frames[shown]!.t).toBeGreaterThanOrEqual(NAVIGATION_PENDING_DELAY_MS);
    const late = frames.slice(shown, swap);
    expect(late.length).toBeGreaterThan(3);
    expect(late.filter((frame) => !frame.bar || !frame.busy)).toEqual([]);

    // Gone in the frame the new page arrives, and stays gone.
    expect(frames.slice(swap).filter((frame) => frame.bar || frame.busy)).toEqual([]);
    await expect(page.getByTestId(PROGRESS_BAR)).toHaveCount(0);
    await expect(page.locator('main')).not.toHaveAttribute('aria-busy');
  });

  test('a navigation faster than the delay shows neither bar nor dim (back and forward)', async ({
    page,
  }) => {
    await openOrigin(page);
    await sidebarLink(page, TARGET).click();
    await expect(page).toHaveURL(new RegExp(`${TARGET}$`), { timeout: NAV_TIMEOUT });
    await expect(page.locator('main h1').first()).toBeVisible();

    for (const [go, landsOn] of [
      [() => page.goBack(), ORIGIN],
      [() => page.goForward(), TARGET],
    ] as const) {
      await startSampling(page);
      await markClick(page);
      await go();
      await expect(page).toHaveURL(new RegExp(`${landsOn}$`), { timeout: NAV_TIMEOUT });
      await page.waitForTimeout(300);
      const { frames } = await stopSampling(page);
      const swap = swapIndex(frames);
      expect(swap, `the page never swapped back to ${landsOn}`).toBeGreaterThanOrEqual(0);
      // The router answers back and forward from its cache, which is what makes this one fast.
      expect(frames[swap]!.t).toBeLessThan(NAVIGATION_PENDING_DELAY_MS);
      expect(frames.filter((frame) => frame.bar || frame.busy)).toEqual([]);
      expect(frames.at(-1)!.active).toEqual([landsOn]);
    }
  });

  test('a newer click takes over: the sidebar stays usable while the page is busy', async ({
    page,
  }) => {
    await openOrigin(page);
    await delayNavigationTo(page, TARGET, HELD_MS);
    await delayNavigationTo(page, OTHER, HELD_MS);

    await sidebarLink(page, TARGET).click();
    await expect(page.locator('main')).toHaveAttribute('aria-busy', 'true');
    await sidebarLink(page, OTHER).click();
    await expect(sidebarLink(page, OTHER)).toHaveAttribute('data-active', 'true');
    await expect(sidebarLink(page, TARGET)).not.toHaveAttribute('data-active', 'true');
    await expect(page).toHaveURL(new RegExp(`${OTHER}$`), { timeout: NAV_TIMEOUT });
    await expect(page.getByTestId(PROGRESS_BAR)).toHaveCount(0);
    await expect(page.locator('main')).not.toHaveAttribute('aria-busy');
  });

  test('a navigation that ends on the error boundary clears the bar and the dim', async ({
    page,
  }) => {
    // `/expenses` refuses a `date_from` that is not a date, so its page read fails for real.
    const broken = `${ROUTES.expenses}?date_from=not-a-date`;
    await openOrigin(page);
    await delayNavigationTo(page, ROUTES.expenses, HELD_MS);
    // A link click as `<Link>` makes it: the click reaches the shell, the router navigates.
    await page.evaluate((href) => {
      const link = document.createElement('a');
      link.href = href;
      link.addEventListener('click', (event) => {
        event.preventDefault();
        (window as unknown as { next: { router: { push(r: string): void } } }).next.router.push(
          href,
        );
      });
      document.body.append(link);
      link.click();
    }, broken);
    await expect(page.locator('main')).toHaveAttribute('aria-busy', 'true');
    await expect(page.getByTestId('error-boundary')).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(page.getByTestId(PROGRESS_BAR)).toHaveCount(0);
    await expect(page.locator('main')).not.toHaveAttribute('aria-busy');
  });

  test('a programmatic query navigation shows the bar only: the page and the nav stay as they are', async ({
    page,
  }) => {
    const route = ROUTES.financeDashboard;
    await dismissAllHints(page);
    await openPage(page, route);
    const picker = page.getByTestId('dashboard-period-picker');
    const preset = picker.locator('[role="radio"][aria-checked="false"]').first();
    await waitForHydration(preset);
    await delayNavigationTo(page, route, HELD_MS);

    await startSampling(page);
    await markClick(page);
    await preset.click();
    await expect(page).toHaveURL(/[?&](period|start_date)=/, { timeout: NAV_TIMEOUT });
    await page.waitForTimeout(200);
    const { frames } = await stopSampling(page);

    const shown = frames.find((frame) => frame.bar);
    expect(shown, 'the bar never showed').toBeDefined();
    expect(shown!.t).toBeGreaterThanOrEqual(NAVIGATION_PENDING_DELAY_MS);
    expect(frames.filter((frame) => frame.busy)).toEqual([]);
    expect(frames.every((frame) => frame.active.join() === route)).toBe(true);
    await expect(page.getByTestId(PROGRESS_BAR)).toHaveCount(0);
  });
});

/*
 * Reduced motion: the bar is a still, full-width line and the page dims without a fade. Each assertion
 * has a twin without `reduce` that requires the motion to be there, so a check that could never see an
 * animation fails instead of passing.
 */
test.describe('navigation feedback and reduced motion', () => {
  test.setTimeout(60_000);
  test.use({ viewport: { width: 1280, height: 900 } });

  for (const reduce of [true, false]) {
    test(`the bar ${reduce ? 'holds still and the dim is instant' : 'sweeps and the dim fades'} (reduced motion ${reduce ? 'on' : 'off'})`, async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: reduce ? 'reduce' : 'no-preference' });
      await openOrigin(page);
      await delayNavigationTo(page, TARGET, HELD_MS * 2);
      await sidebarLink(page, TARGET).click();
      const bar = page.getByTestId(PROGRESS_BAR);
      await expect(bar).toBeVisible();

      const fill = await bar.evaluate((element) => {
        const segment = element.firstElementChild as HTMLElement;
        const style = getComputedStyle(segment);
        return {
          animation: style.animationName,
          width: segment.getBoundingClientRect().width,
          barWidth: element.getBoundingClientRect().width,
        };
      });
      const dim = await page.locator('main').evaluate((element) => {
        const style = getComputedStyle(element);
        return { property: style.transitionProperty, duration: style.transitionDuration };
      });
      if (reduce) {
        expect(fill.animation).toBe('none');
        expect(fill.width).toBeCloseTo(fill.barWidth, 0);
        expect(dim.property).toBe('none');
      } else {
        expect(fill.animation).toBe('navigation-progress');
        expect(fill.width).toBeLessThan(fill.barWidth);
        expect(dim.property).toBe('opacity');
        expect(dim.duration).not.toBe('0s');
      }
      await expect(page).toHaveURL(new RegExp(`${TARGET}$`), { timeout: NAV_TIMEOUT });
    });
  }
});
