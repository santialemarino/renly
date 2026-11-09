import { expect, request as playwrightRequest, test, type Page } from '@playwright/test';

import { ROUTES } from '@/config/routes';
import { API_BASE, apiToken, WEB_BASE } from './helpers/api';
import { ADMIN_AUTH_STATE_PATH, e2eAdminCredentials } from './helpers/auth';
import { testMarker } from './helpers/factories';

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
// The popover's gap from the sidebar's edge (`POPOVER_GAP_PX` in the bell).
const GAP_PX = 8;
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

  /*
   * The distance to the sidebar's edge is measured, so it has to be measured again while the popover is
   * open whenever the layout moves under it. A larger text size scales the sidebar and the header's
   * padding with it (both are in rem) without any resize event, and the window can then resize too; the
   * popover must sit the same gap past the sidebar's edge after each.
   */
  test('keeps its gap from the sidebar while the layout changes under it', async ({ page }) => {
    await openStart(page, 1440);
    const bell = page.getByTestId(BELL);
    await bell.click();
    const panel = page.getByTestId(PANEL);
    await expect(panel).toBeVisible();
    await page.waitForTimeout(400);

    const expectGap = async (when: string) => {
      const sidebar = await box(page, SIDEBAR);
      const panelBox = (await panel.boundingBox())!;
      expect(
        Math.abs(panelBox.x - (sidebar.x + sidebar.width + GAP_PX)),
        `the panel is not ${GAP_PX}px past the sidebar ${when}`,
      ).toBeLessThanOrEqual(TOLERANCE_PX);
    };
    await expectGap('on open');

    const headerPadding = () =>
      bell.evaluate((element) => getComputedStyle(element.parentElement!).paddingRight);
    const before = await headerPadding();
    await page.evaluate(() => {
      document.documentElement.style.fontSize = '32px';
    });
    // Proven to have moved the bell inside the header, which is what the old offset no longer fits.
    await expect.poll(headerPadding).not.toBe(before);
    await expect(panel).toBeVisible();
    await expect.poll(async () => (await panel.boundingBox())?.x).toBeGreaterThan(0);
    await page.waitForTimeout(200);
    await expectGap('after the text size grew');

    await page.setViewportSize({ width: 1280, height: HEIGHT });
    await page.waitForTimeout(200);
    await expect(panel).toBeVisible();
    await expectGap('after the window resized');
  });

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

/*
 * The unread count after a read made somewhere other than the bell. The bell's rows and count come
 * from the protected layout and are re-read by `router.refresh()`; it once copied them into state on
 * mount, so after marking read in the inbox (one row, or all of them) the bell kept the old count until
 * a full reload.
 *
 * Notifications only ever reach someone through another person's act, so a second account makes them:
 * the harness opens two groups and invites the admin account into each, and the admin accepting each
 * invite tells the harness ("… joined …"). Both groups are deleted afterwards. Needs the admin
 * account, like the admin scans; CI always has it.
 */
test.describe('the bell after reads made elsewhere', () => {
  test.skip(!e2eAdminCredentials(), 'needs E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD');

  const groupIds: number[] = [];
  let headers: Record<string, string>;

  // The admin account's API token, read from its saved session as `apiToken()` reads the harness one.
  async function adminToken(): Promise<string> {
    const context = await playwrightRequest.newContext({
      baseURL: WEB_BASE,
      storageState: ADMIN_AUTH_STATE_PATH,
    });
    try {
      const response = await context.get('/api/auth/session');
      expect(response.ok()).toBe(true);
      return (await response.json()).user.accessToken as string;
    } finally {
      await context.dispose();
    }
  }

  test.beforeAll(async () => {
    headers = { Authorization: `Bearer ${await apiToken()}` };
    const admin = { Authorization: `Bearer ${await adminToken()}` };
    const api = await playwrightRequest.newContext();
    try {
      // Whatever an earlier spec left unread does not matter: everything starts read.
      await api.post(`${API_BASE}/notifications/read-all`, { headers });
      for (const label of ['one', 'two']) {
        const group = await api.post(`${API_BASE}/groups`, {
          headers,
          data: { name: `${testMarker(`bell-${label}`)}`, kind: 'other' },
        });
        expect(group.ok(), `POST /groups: ${group.status()}`).toBe(true);
        const groupId: number = (await group.json()).id;
        groupIds.push(groupId);
        const seat = await api.post(`${API_BASE}/groups/${groupId}/members`, {
          headers,
          data: { display_name: 'E2E admin' },
        });
        expect(seat.ok(), `POST members: ${seat.status()}`).toBe(true);
        const members = (await seat.json()).members as { id: number; display_name: string }[];
        const seatId = members.find((member) => member.display_name === 'E2E admin')!.id;
        const invite = await api.post(`${API_BASE}/groups/${groupId}/members/${seatId}/invite`, {
          headers,
          data: {},
        });
        expect(invite.ok(), `POST invite: ${invite.status()}`).toBe(true);
        const token = new URL((await invite.json()).invite_url).searchParams.get('token');
        const accepted = await api.post(`${API_BASE}/group-invites/${token}/accept`, {
          headers: admin,
        });
        expect(accepted.ok(), `accept: ${accepted.status()} ${await accepted.text()}`).toBe(true);
      }
    } finally {
      await api.dispose();
    }
  });

  test.afterAll(async () => {
    const api = await playwrightRequest.newContext();
    for (const groupId of groupIds) await api.delete(`${API_BASE}/groups/${groupId}`, { headers });
    await api.dispose();
  });

  test('follows a read in the inbox, then "Mark all read" there', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: HEIGHT });
    await page.goto(ROUTES.notifications);
    const bell = page.getByTestId(BELL);
    await expect(bell).toHaveAccessibleName('2 unread notifications');

    // Opening one navigates to its group; the bell there must already count one fewer.
    await page
      .locator('main')
      .getByRole('link', { name: /joined/ })
      .first()
      .click();
    await expect(page).not.toHaveURL(ROUTES.notifications);
    await expect(bell).toHaveAccessibleName('1 unread notification');

    await page.goto(ROUTES.notifications);
    await expect(bell).toHaveAccessibleName('1 unread notification');
    await page.locator('main').getByRole('button', { name: 'Mark all read' }).click();
    await expect(bell).toHaveAccessibleName('No notifications');
  });
});
