import { expect, test, type Page } from '@playwright/test';

import { ROUTES } from '@/config/routes';

/*
 * Where the bell opens, and where its links lead.
 *
 * On a desktop the sidebar is a column and the bell sits in its header, so the popover opens to the
 * sidebar's RIGHT, top-aligned with the bell, entirely over the page — it once opened below the bell
 * and straddled the column and the content. Below `md` the sidebar is a Sheet, and the bell opens a
 * full-width panel over it instead. Both are geometry, which only a browser can measure.
 *
 * The links: "See all" opens the inbox at `/notifications`, the inbox links to the settings at
 * `/notifications/settings`.
 */

// Where each test starts: a page with no notification UI of its own.
const START = ROUTES.alerts;
const BELL = 'notification-bell';
const PANEL = 'notification-panel';
const SIDEBAR = '[data-slot="sidebar-container"]';
const HAMBURGER = '[data-sidebar="trigger"]';

// Sub-pixel rounding only.
const TOLERANCE_PX = 2;
// The popover keeps at least this much from the viewport's bottom edge (its collision padding).
const MIN_BOTTOM_ROOM_PX = 8;

const DESKTOP_WIDTHS = [768, 1280, 1440] as const;
const PHONE_WIDTH = 390;
const HEIGHT = 900;

async function openStart(page: Page, width: number, height = HEIGHT) {
  await page.setViewportSize({ width, height });
  await page.goto(START);
  await expect(page.locator('main h1')).toBeVisible();
}

async function box(page: Page, selector: string) {
  const found = await page.locator(selector).first().boundingBox();
  expect(found, `${selector} has no box`).not.toBeNull();
  return found!;
}

test.describe('the notification bell', () => {
  for (const width of DESKTOP_WIDTHS) {
    test(`opens beside the sidebar, top-aligned with the bell, at ${width}px`, async ({ page }) => {
      await openStart(page, width);
      const bell = page.getByTestId(BELL);
      await bell.click();
      const panel = page.getByTestId(PANEL);
      await expect(panel).toBeVisible();
      // The open animation scales and slides the panel; measure where it comes to rest.
      await page.waitForTimeout(400);

      const sidebar = await box(page, SIDEBAR);
      const bellBox = (await bell.boundingBox())!;
      const panelBox = (await panel.boundingBox())!;
      expect(panelBox.x, 'the panel overlaps the sidebar').toBeGreaterThanOrEqual(
        sidebar.x + sidebar.width - TOLERANCE_PX,
      );
      expect(
        Math.abs(panelBox.y - bellBox.y),
        'the panel is not top-aligned with the bell',
      ).toBeLessThanOrEqual(TOLERANCE_PX);
      expect(panelBox.x + panelBox.width, 'the panel runs off the viewport').toBeLessThanOrEqual(
        width,
      );

      // Escape closes it and gives focus back to the bell.
      await page.keyboard.press('Escape');
      await expect(panel).toHaveCount(0);
      await expect(bell).toBeFocused();
    });
  }

  test('fits a short viewport and scrolls its list rather than the page', async ({ page }) => {
    const height = 420;
    await openStart(page, 1280, height);
    await page.getByTestId(BELL).click();
    const panel = page.getByTestId(PANEL);
    await expect(panel).toBeVisible();
    await page.waitForTimeout(400);
    const panelBox = (await panel.boundingBox())!;
    expect(panelBox.y + panelBox.height).toBeLessThanOrEqual(height - MIN_BOTTOM_ROOM_PX);
    // Its last element, the way to the inbox, is still on screen.
    await expect(page.getByTestId('notification-see-all')).toBeInViewport();
  });

  test(`opens as a full-width panel over the menu at ${PHONE_WIDTH}px`, async ({ page }) => {
    await openStart(page, PHONE_WIDTH);
    await page.locator(HAMBURGER).click();
    const bell = page.getByTestId(BELL);
    await bell.click();
    const panel = page.getByTestId(PANEL);
    await expect(panel).toBeVisible();
    await page.waitForTimeout(600);

    const panelBox = (await panel.boundingBox())!;
    expect(panelBox.x).toBeLessThanOrEqual(TOLERANCE_PX);
    expect(panelBox.width).toBeGreaterThanOrEqual(PHONE_WIDTH - TOLERANCE_PX);

    // Escape closes the panel only: the menu it was opened from is still there, focus on the bell.
    await page.keyboard.press('Escape');
    await expect(panel).toHaveCount(0);
    await expect(bell).toBeVisible();
    await expect(bell).toBeFocused();
  });

  test('"See all" opens the inbox, which links to the settings', async ({ page }) => {
    await openStart(page, 1280);
    await page.getByTestId(BELL).click();
    await page.getByTestId('notification-see-all').click();
    await expect(page).toHaveURL(ROUTES.notifications);

    await page.getByTestId('notification-settings-link').click();
    await expect(page).toHaveURL(ROUTES.notificationSettings);
    await expect(page.getByTestId('notification-digest-switch')).toBeVisible();
  });
});
