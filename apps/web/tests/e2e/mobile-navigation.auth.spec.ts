import { expect, test } from '@playwright/test';

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

const DASHBOARD = ROUTES.dashboard;

// The nav list inside the sidebar, and the trigger that opens it on small screens.
const NAV = '[data-testid="sidebar-nav"]';
const TRIGGER = '[data-sidebar="trigger"]';

// A navigation on a dev server is slow enough to exceed Playwright's 5s default. Measured while
// building this: 8.7s cold, 2.6s warm — at the default the spec failed three runs out of four, which
// is worse than no spec at all because it trains people to ignore it.
const NAV_TIMEOUT = 20_000;

test.describe('mobile navigation (signed in)', () => {
  test('below the breakpoint the nav is reachable through the trigger', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(DASHBOARD);

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

  test('a destination inside a collapsed group navigates, and the sheet closes on the tap', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(DASHBOARD);

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
     * The sheet must be gone BEFORE the navigation resolves, not after. On a phone it is a full
     * overlay, so a sheet that waits for the route to change leaves the reader staring at the menu
     * they just tapped — for over two seconds on a cold server. Asserting the close first, with a
     * short timeout, is what distinguishes "closed on the tap" from "closed on arrival".
     */
    await expect(page.locator(NAV)).toHaveCount(0, { timeout: 2_000 });
    await expect(page).toHaveURL(new RegExp(`${ROUTES.expenses}$`), { timeout: NAV_TIMEOUT });
  });

  test('the trigger and the permanent sidebar swap at the breakpoint, with no width holding both or neither', async ({
    page,
  }) => {
    /*
     * Each width gets its own LOAD rather than a resize of the previous one. `useIsMobile()` seeds its
     * state on mount, so a programmatic resize alone leaves the sidebar rendering for the old width —
     * verified by hand while building this unit, where 767→768 without a reload still reported the
     * Sheet in charge. A resize-only spec would fail on correct code, which is the worst kind to leave.
     */
    await page.setViewportSize({ width: 767, height: 900 });
    await page.goto(DASHBOARD);
    await expect(page.locator(TRIGGER)).toBeVisible();
    await expect(page.locator(NAV)).toHaveCount(0);

    // At 768 the sidebar is permanent, so the trigger is redundant. Asserted as "present in the DOM
    // but not visible" rather than `toBeHidden()` alone, which is also satisfied by an element that
    // does not exist — the weaker reading this file refuses two tests above.
    await page.setViewportSize({ width: 768, height: 900 });
    await page.goto(DASHBOARD);
    await expect(page.locator(NAV)).toBeVisible();
    await expect(page.locator(TRIGGER)).toHaveCount(1);
    await expect(page.locator(TRIGGER)).toBeHidden();
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
    await page.goto(DASHBOARD);

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
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(DASHBOARD);

    // The layout used to nest a second `<main>` inside the one `SidebarInset` rendered, which is what
    // `landmark-no-duplicate-main` and `landmark-main-is-top-level` fire on.
    await expect(page.locator('main')).toHaveCount(1);

    // And the placement half, which the count alone cannot see: a `header` inside `main` maps to
    // generic, so the banner would be lost. Asserted at a mobile width, because that is the only
    // place the header is rendered at all.
    await expect(page.locator(`main ${TRIGGER}`)).toHaveCount(0);
    await expect(page.locator('body > div header, header')).toHaveCount(1);
  });
});
