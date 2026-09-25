import { expect, test, type Page } from '@playwright/test';

import { ROUTES } from '@/config/routes';

/*
 * Navigation below the mobile breakpoint, which is the one thing about the sidebar that NO other kind
 * of test can see.
 *
 * Under that width the sidebar renders as a Radix Sheet, and a CLOSED Sheet is unmounted — so the nav
 * is not merely hidden, it is absent from the DOM. Every static check therefore passes on the broken
 * state: the component exists, it is exported, it type-checks, and a jsdom render mounts it happily
 * because jsdom has no viewport width that makes `useIsMobile()` true the way a real layout does. The
 * defect this pins shipped exactly that way — `SidebarTrigger` was defined and exported for months
 * and rendered nowhere, leaving every route below the breakpoint with no way to reach any other
 * route, quick-add, the currency switcher, settings, or sign-out.
 */

/*
 * Where every test starts, and deliberately NOT the dashboard. The harness account is real, and on an
 * account that has not finished onboarding the dashboard auto-starts the welcome tour: a modal overlay
 * that swallows the trigger's click and renders a `<header>` of its own. The tour runs on the
 * dashboard only, so starting anywhere else makes the spec about navigation rather than about one
 * account's onboarding history. /snapshots sits in the Portfolio group, which leaves Finances
 * collapsed for the two-tap journey below.
 */
const START = ROUTES.snapshots;
const PHONE = { width: 390, height: 844 };

// The nav list inside the sidebar, the trigger that opens it on small screens, and the bar holding it.
const NAV = '[data-testid="sidebar-nav"]';
const TRIGGER = '[data-sidebar="trigger"]';
const BAR = 'mobile-nav-bar';

// A navigation on a dev server is slow enough to exceed Playwright's 5s default. Measured while
// building this: 8.7s cold, 2.6s warm — at the default the spec failed three runs out of four, which
// is worse than no spec at all because it trains people to ignore it.
const NAV_TIMEOUT = 20_000;

/*
 * Holds every request for `path` until the returned function is called — the page's own document and
 * the client router's fetch of it alike, since both carry the pathname.
 *
 * This is what lets a test say "before the page arrives" without racing the server. A sheet that
 * closes only when the route changes cannot close while its destination is held, so the assertion
 * fails on that code however fast the machine is — instead of passing whenever the page happened to
 * load inside a short timeout, which is what a timing-based version of the same check does.
 */
async function holdRequestsTo(page: Page, path: string): Promise<() => void> {
  let release = () => {};
  const released = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(
    (url) => url.pathname === path,
    async (route) => {
      await released;
      await route.continue();
    },
  );
  return release;
}

test.describe('mobile navigation (signed in)', () => {
  test('below the breakpoint the nav is reachable through the trigger', async ({ page }) => {
    await page.setViewportSize(PHONE);
    await page.goto(START);

    // The starting state the defect made permanent: the Sheet is closed, so the nav really is absent
    // rather than merely off-screen. Asserting "not visible" would also pass with no trigger at all,
    // which is the state this spec exists to refuse.
    await expect(page.locator(NAV)).toHaveCount(0);

    const trigger = page.locator(TRIGGER);
    await expect(trigger).toBeVisible();
    await trigger.click();

    // The nav is now mounted AND carries real destinations: a Sheet that opened onto an empty panel
    // would satisfy a bare visibility check. Asserted on the top-level items, because the rest sit
    // inside collapsed groups — see the next test.
    await expect(page.locator(NAV)).toBeVisible();
    await expect(page.locator(`${NAV} a[href="${ROUTES.dashboard}"]`)).toBeVisible();
  });

  test('tapping a destination closes the sheet before the page arrives', async ({ page }) => {
    await page.setViewportSize(PHONE);
    await page.goto(START);
    const release = await holdRequestsTo(page, ROUTES.expenses);

    try {
      await page.locator(TRIGGER).click();

      /*
       * Every route but the dashboard lives inside a collapsed group, so the real journey is two taps:
       * open the group, then pick the destination. Written out rather than reaching for the link
       * directly, because the link does not EXIST until the group expands — a spec that skipped this
       * step would fail for a reason that has nothing to do with what it is testing.
       */
      await page
        .locator(NAV)
        .getByRole('button', { name: /finances|finanzas/i })
        .click();
      await page.locator(`${NAV} a[href="${ROUTES.expenses}"]`).click();

      /*
       * The destination is held, so the route has not changed and cannot until it is released — the
       * tap is the only thing left that can close the sheet. On a phone the sheet is a full overlay,
       * and one that waits for the route leaves the reader staring at the menu they just tapped for
       * as long as the server takes.
       */
      await expect(page.locator(NAV)).toHaveCount(0);
      await expect(page).toHaveURL(new RegExp(`${START}$`));
    } finally {
      release();
    }

    await expect(page).toHaveURL(new RegExp(`${ROUTES.expenses}$`), { timeout: NAV_TIMEOUT });
  });

  test('tapping the page you are already on closes the sheet', async ({ page }) => {
    /*
     * The case a route-change close can never handle, because the route does not change: the sheet
     * used to stay up over the page with nothing left to dismiss it but the backdrop. Its group is
     * already open — a group holding the active page starts expanded — so this is one tap.
     */
    await page.setViewportSize(PHONE);
    await page.goto(ROUTES.expenses);

    await page.locator(TRIGGER).click();
    await expect(page.locator(NAV)).toBeVisible();
    await page.locator(`${NAV} a[href="${ROUTES.expenses}"]`).click();

    await expect(page.locator(NAV)).toHaveCount(0);
    await expect(page).toHaveURL(new RegExp(`${ROUTES.expenses}$`));
  });

  test('the trigger and the permanent sidebar swap at the breakpoint, with no width holding both or neither', async ({
    page,
  }) => {
    /*
     * One load, then resizes in both directions. `useIsMobile()` follows its media query's `change`
     * event, so crossing the breakpoint swaps the Sheet and the permanent sidebar live — the way a
     * tablet rotating or a desktop window being narrowed crosses it — and that live switch is part of
     * what is under test.
     */
    await page.setViewportSize({ width: 767, height: 900 });
    await page.goto(START);
    await expect(page.locator(TRIGGER)).toBeVisible();
    await expect(page.locator(NAV)).toHaveCount(0);

    // At 768 the sidebar is permanent, so the trigger is redundant. Asserted as "present in the DOM
    // but not visible" rather than `toBeHidden()` alone, which is also satisfied by an element that
    // does not exist — the weaker reading this file refuses above.
    await page.setViewportSize({ width: 768, height: 900 });
    await expect(page.locator(NAV)).toBeVisible();
    await expect(page.locator(TRIGGER)).toHaveCount(1);
    await expect(page.locator(TRIGGER)).toBeHidden();

    await page.setViewportSize({ width: 767, height: 900 });
    await expect(page.locator(TRIGGER)).toBeVisible();
    await expect(page.locator(NAV)).toHaveCount(0);
  });

  test('the breakpoint holds when the reader has changed their browser font size', async ({
    page,
  }) => {
    /*
     * THE regression this unit nearly shipped. Tailwind compiles `md:` to `@media (min-width: 48rem)`,
     * which resolves against the browser's default font size, while `useIsMobile()` used to compare
     * `window.innerWidth` against 768 PIXELS. Those are the same number only at a 16px root.
     *
     * Set Chrome's font size to Large and `md` moves to 960px while the hook stayed at 768 — so
     * between them the CSS hid the sidebar, showed this bar, and the hook still said "not mobile",
     * making `toggleSidebar()` a no-op. A visible navigation button that did nothing, and no other way
     * in. Every other test here runs at the default 16px and cannot see it.
     */
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Page.setFontSizes', { fontSizes: { standard: 20, fixed: 20 } });

    await page.setViewportSize({ width: 900, height: 900 });
    await page.goto(START);

    const trigger = page.locator(TRIGGER);
    if (await trigger.isVisible()) {
      // The bar is showing, so this width must be the Sheet's — the trigger has to actually open it.
      await trigger.click();
      await expect(page.locator(NAV)).toBeVisible();
    } else {
      // Otherwise the permanent sidebar must be the one in charge. What must never happen is neither.
      await expect(page.locator(NAV)).toBeVisible();
    }
  });

  test('the page has exactly one main landmark, and the mobile header is not inside it', async ({
    page,
  }) => {
    await page.setViewportSize(PHONE);
    await page.goto(START);

    // The layout used to nest a second `<main>` inside the one `SidebarInset` rendered, which is what
    // `landmark-no-duplicate-main` and `landmark-main-is-top-level` fire on.
    await expect(page.locator('main')).toHaveCount(1);

    // And the placement half, which the count alone cannot see: a `header` inside `main` maps to
    // generic, so the banner would be lost. Asserted on the bar itself rather than on every `header`
    // on the page, since other surfaces render their own; and at a mobile width, because that is the
    // only place the bar is rendered at all.
    const bar = page.getByTestId(BAR);
    await expect(bar).toHaveCount(1);
    await expect(bar).toHaveRole('banner');
    await expect(page.locator(`main [data-testid="${BAR}"]`)).toHaveCount(0);
  });
});
