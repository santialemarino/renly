import { expect, test } from '@playwright/test';

import { ROUTES } from '@/config/routes';
import {
  dismissAllHints,
  markClick,
  NAV_TIMEOUT,
  openNavGroups,
  openPage,
  sidebarLink,
  sidebarRoutes,
  startSampling,
  stopSampling,
  swapIndex,
  textsFrom,
} from './helpers/navigation';

/*
 * A navigation keeps the old page on screen until the new one is complete, then swaps it in at once:
 * `<main>` is never empty on the way, never shows the two pages together, nothing stands in for the new
 * page (its first frame already reads as it does once settled), and nothing moves on the swap.
 *
 * What it guards against is a route loading state. A `loading.tsx` is mounted the moment a navigation
 * starts — the old page goes and `<main>` is empty or a placeholder — and React then keeps it for
 * ~300 ms however soon the page is ready, which is what every click used to cost. A fade on the swap
 * would show up here too, as frames holding both pages.
 *
 * Every page the sidebar links to (derived from `config/nav.ts`) is entered by a real click on its link
 * from another page, and every animation frame is sampled from the click until the new page's text is
 * on screen and settled. Measured on a production build: a dev server compiles on first visit and
 * prefetches nothing, which is not what users get.
 */

// Where each navigation starts: /alerts (a page with nothing of its own to settle), or /preferences for
// /alerts itself. Not the dashboard, which starts the welcome tour on an account still onboarding.
function originFor(route: string) {
  return route === ROUTES.alerts ? ROUTES.preferences : ROUTES.alerts;
}

// The frames after the new page's first one that are still settling (a streamed section, a hint).
const SETTLE_MS = 400;

test.describe('navigating between pages', () => {
  test.setTimeout(60_000);
  test.use({ viewport: { width: 1280, height: 900 } });

  test('covers every page the sidebar links to', () => {
    expect(sidebarRoutes().length).toBeGreaterThanOrEqual(20);
  });

  for (const route of sidebarRoutes()) {
    test(`${route}: the old page stays until the new one swaps in, with nothing blank between`, async ({
      page,
    }) => {
      // A hint revealing itself after the swap is motion of its own, not the swap's.
      await dismissAllHints(page);
      await openPage(page, originFor(route));
      await openNavGroups(page);
      const link = sidebarLink(page, route);
      await expect(link).toBeVisible();

      await startSampling(page);
      await markClick(page);
      await link.click();
      await expect(page).toHaveURL(new RegExp(`${route}$`), { timeout: NAV_TIMEOUT });
      await expect(page.locator('main h1').first()).toBeVisible({ timeout: NAV_TIMEOUT });
      await page.waitForTimeout(SETTLE_MS);
      const { frames, shifts } = await stopSampling(page);

      const swap = swapIndex(frames);
      expect(swap, `${route}: the new page never showed`).toBeGreaterThan(0);
      const blank = frames.filter((frame) => !frame.old && !frame.fresh);
      const both = frames.filter((frame) => frame.old && frame.fresh);
      expect(blank, `${route}: <main> showed nothing in ${blank.length} frames`).toEqual([]);
      expect(both, `${route}: both pages showed in ${both.length} frames`).toEqual([]);
      // Before the swap the old page, and from it the new one only — whole: the first frame of the new
      // page already reads as it does once settled, so nothing stood in for it on the way.
      expect(frames.slice(0, swap).every((frame) => frame.old)).toBe(true);
      expect(frames.slice(swap).every((frame) => frame.fresh && !frame.old)).toBe(true);
      expect(
        new Set(textsFrom(frames, swap)).size,
        `${route}: the new page's text changed after it swapped in (a stand-in, then the page)`,
      ).toBe(1);
      // Nothing that was on screen moved: the old page leaves whole and the new one arrives whole.
      expect(
        shifts.reduce((sum, value) => sum + value, 0),
        `${route}: layout shift`,
      ).toBe(0);
    });
  }
});
