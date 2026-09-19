import { expect, test } from '@playwright/test';

import { ROUTES } from '@/config/routes';

/*
 * Navigation below the mobile breakpoint, which is the one thing about the sidebar that NO other kind
 * of test can see.
 *
 * Under `MOBILE_BREAKPOINT` the sidebar renders as a Radix Sheet, and a CLOSED Sheet is unmounted — so
 * the nav is not merely hidden, it is absent from the DOM. Every static check therefore passes on the
 * broken state: the component exists, it is exported, it type-checks, and a jsdom render of the
 * sidebar mounts it happily because jsdom has no viewport width that makes `useIsMobile()` true in the
 * way a real layout does. The defect this pins shipped exactly that way — `SidebarTrigger` was defined
 * and exported for months and rendered nowhere, leaving every route under 768px with no way to reach
 * any other route, quick-add, the currency switcher, settings, or sign-out.
 *
 * The widths are asserted as BEHAVIOUR at the boundary rather than against an imported constant. The
 * breakpoint is declared twice by design — `MOBILE_BREAKPOINT` in `packages/ui/src/hooks/use-mobile.ts`
 * and Tailwind's `md` in the bar's own `md:hidden` — and a test that imported one of them could not
 * see the two disagreeing. Driving 767 and 768 pins the seam itself, so moving either number without
 * the other fails here.
 */

const DASHBOARD = ROUTES.dashboard;

// The nav list inside the sidebar, and the trigger that opens it on small screens.
const NAV = '[data-testid="sidebar-nav"]';
const TRIGGER = '[data-sidebar="trigger"]';

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

    // The nav is now mounted AND it carries real destinations: a Sheet that opened onto an empty
    // panel would satisfy a bare visibility check. Asserted on the top-level items, because the rest
    // sit inside collapsed groups — see the next test.
    await expect(page.locator(NAV)).toBeVisible();
    await expect(page.locator(`${NAV} a[href="${ROUTES.dashboard}"]`)).toBeVisible();
  });

  test('a destination inside a collapsed group actually navigates, and the sheet closes behind it', async ({
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

    await expect(page).toHaveURL(new RegExp(`${ROUTES.expenses}$`));

    /*
     * And the sheet must be GONE. On a phone it is a full overlay, so leaving it open means the
     * reader taps a destination, the page changes behind the panel, and they are left looking at the
     * menu they just used. Asserting the URL alone would pass on exactly that.
     */
    await expect(page.locator(NAV)).toHaveCount(0);
  });

  test('the trigger and the permanent sidebar swap at the breakpoint, with no width holding both or neither', async ({
    page,
  }) => {
    /*
     * Each width gets its own LOAD rather than a resize of the previous one. `useIsMobile()` seeds
     * its state on mount, so a programmatic resize alone leaves the sidebar rendering for the old
     * width — verified by hand while building this unit, where 767→768 without a reload still
     * reported the Sheet in charge. A resize-only spec would therefore fail on correct code, which
     * is the worst kind of test to leave behind.
     */
    // 767: the Sheet is in charge, so the trigger must be the way in.
    await page.setViewportSize({ width: 767, height: 900 });
    await page.goto(DASHBOARD);
    await expect(page.locator(TRIGGER)).toBeVisible();
    await expect(page.locator(NAV)).toHaveCount(0);

    // 768: the sidebar is permanent, so the trigger is redundant and must not be shown. A width where
    // BOTH appear is the bug in the other direction, and one where NEITHER does is the original bug.
    await page.setViewportSize({ width: 768, height: 900 });
    await page.goto(DASHBOARD);
    await expect(page.locator(NAV)).toBeVisible();
    await expect(page.locator(TRIGGER)).toBeHidden();
  });

  test('the page exposes exactly one main landmark', async ({ page }) => {
    await page.goto(DASHBOARD);

    // `SidebarInset` already renders the page's `<main>`; the layout used to nest a second one inside
    // it, which is three axe landmark violations on every protected route. Asserted here because the
    // mobile bar is a sibling of that element and the count is what makes its placement correct.
    await expect(page.locator('main')).toHaveCount(1);
  });
});
