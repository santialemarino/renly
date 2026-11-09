import { expect, request as playwrightRequest, test, type Page } from '@playwright/test';

import { ROUTES } from '@/config/routes';
import { API_BASE, apiToken } from './helpers/api';
import { testMarker } from './helpers/factories';

/*
 * The accounts and credit-cards tables at a phone's width. Both once scrolled sideways at 390px: the
 * balance and the row actions sat past the right edge, and an expanded row's panel scrolled with them.
 * Now each row is name, balance and actions there, and the panel fits the table rather than widening it.
 *
 * Asserted through the table's own scroll container (`data-overflowing`, which the `Table` sets while
 * its content is wider than its column) and through the balance being on screen, with the row expanded
 * — the state the panel used to widen.
 */

const PHONE = { width: 390, height: 844 };
const DESKTOP = { width: 1440, height: 900 };

async function expectFits(page: Page, marker: string) {
  const row = page.getByRole('row').filter({ hasText: marker }).first();
  await expect(row).toBeVisible();
  await row.getByRole('button', { expanded: false }).click();
  await expect(row.getByRole('button', { expanded: true })).toBeVisible();
  // The panel opens with a height animation and loads its history after a display floor; measure
  // once it has come to rest.
  await expect(page.getByText(/^Loading/)).toHaveCount(0);
  await page.waitForTimeout(400);

  const container = page.locator('[data-slot="table-container"]').first();
  const overflow = () => container.evaluate((element) => element.scrollWidth - element.clientWidth);
  await expect
    .poll(overflow, { message: 'the table is wider than the phone' })
    .toBeLessThanOrEqual(0);
  await expect(container).toHaveAttribute('data-overflowing', 'false');
  // The figure the row is for, whole and on screen.
  await expect(row.locator('[data-money]:visible').first()).toBeInViewport({ ratio: 1 });
}

test.describe('money lists at a phone’s width (signed in)', () => {
  let headers: Record<string, string>;
  let marker: string;
  let accountId: number;
  let cardId: number;

  test.beforeAll(async () => {
    headers = { Authorization: `Bearer ${await apiToken()}` };
    marker = testMarker('phone');
    const api = await playwrightRequest.newContext();
    try {
      const account = await api.post(`${API_BASE}/accounts`, {
        headers,
        data: {
          name: `${marker} Caja de ahorro`,
          type: 'bank',
          currency: 'ARS',
          opening_balance: '123456789.12',
          opening_date: new Date().toISOString().slice(0, 10),
        },
      });
      expect(account.ok(), `POST /accounts: ${account.status()} ${await account.text()}`).toBe(
        true,
      );
      accountId = (await account.json()).id;
      const card = await api.post(`${API_BASE}/credit-cards`, {
        headers,
        data: { name: `${marker} Visa`, closing_day: 5, due_day: 15, currency: 'ARS' },
      });
      expect(card.ok(), `POST /credit-cards: ${card.status()} ${await card.text()}`).toBe(true);
      cardId = (await card.json()).id;
    } finally {
      await api.dispose();
    }
  });

  test.afterAll(async () => {
    const api = await playwrightRequest.newContext();
    await api.delete(`${API_BASE}/accounts/${accountId}`, { headers });
    await api.delete(`${API_BASE}/credit-cards/${cardId}`, { headers });
    await api.dispose();
  });

  for (const [route, label] of [
    [ROUTES.accounts, 'accounts'],
    [ROUTES.creditCards, 'credit cards'],
  ] as const) {
    test(`${label}: name, balance and actions fit at 390px, expanded too`, async ({ page }) => {
      await page.setViewportSize(PHONE);
      await page.goto(`${route}?search=${encodeURIComponent(marker)}`);
      await expectFits(page, marker);
    });

    test(`${label}: every column is back from md up`, async ({ page }) => {
      await page.setViewportSize(DESKTOP);
      await page.goto(`${route}?search=${encodeURIComponent(marker)}`);
      const headerCells = page.locator('thead th');
      await expect(headerCells).toHaveCount(route === ROUTES.accounts ? 8 : 7);
      for (const cell of await headerCells.all()) await expect(cell).toBeVisible();
    });
  }
});
