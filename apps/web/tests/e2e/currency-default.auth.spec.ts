import { expect, request as playwrightRequest, test, type Page } from '@playwright/test';

import { API_BASE, apiToken, WEB_BASE } from './helpers/api';
import { expenseRow, testMarker } from './helpers/factories';

/*
 * With no `active-currency` cookie (a first visit, cleared cookies, a new device) the pages must convert
 * to the primary currency, which is what the sidebar's switcher shows selected. They once showed the
 * ORIGINAL amounts instead while the switcher claimed the primary, and clicking the selected pill could
 * not fix it.
 *
 * Asserted relatively, so no rate is frozen into the spec: the row's amount with no cookie must read
 * exactly as it does with the primary chosen explicitly, and differently from "original".
 */

const COOKIE = 'active-currency';
const ORIGINAL = 'original';

async function amountWith(page: Page, marker: string, cookie: string | null): Promise<string> {
  await page.context().clearCookies({ name: COOKIE });
  if (cookie !== null) {
    await page.context().addCookies([{ name: COOKIE, value: cookie, url: WEB_BASE }]);
  }
  await page.goto(`/expenses?search=${encodeURIComponent(marker)}`);
  const row = expenseRow(page, marker);
  await expect(row).toHaveCount(1);
  // The amount column is the second cell after the date.
  return (await row.getByRole('cell').nth(1).innerText()).trim();
}

test.describe('the display currency with no saved choice (signed in)', () => {
  let marker: string;
  let expenseId: number;
  let primary: string;
  let headers: Record<string, string>;

  test.beforeAll(async () => {
    headers = { Authorization: `Bearer ${await apiToken()}` };
    const api = await playwrightRequest.newContext();
    try {
      const settings = await (await api.get(`${API_BASE}/settings`, { headers })).json();
      primary = settings.primary_currency ?? 'ARS';
      // Any currency the account does not keep its books in, so a conversion is visible.
      const foreign = primary === 'USD' ? 'EUR' : 'USD';
      marker = testMarker('currency-default');
      const created = await api.post(`${API_BASE}/expenses`, {
        headers,
        data: {
          date: new Date().toISOString().slice(0, 10),
          amount: '10.00',
          currency: foreign,
          category: 'other',
          notes: marker,
        },
      });
      expect(created.ok(), `POST /expenses: ${created.status()} ${await created.text()}`).toBe(
        true,
      );
      expenseId = (await created.json()).id;
    } finally {
      await api.dispose();
    }
  });

  test.afterAll(async () => {
    const api = await playwrightRequest.newContext();
    await api.delete(`${API_BASE}/expenses/${expenseId}`, { headers });
    await api.dispose();
  });

  test('converts a foreign row to the primary currency, like the switcher says', async ({
    page,
  }) => {
    const original = await amountWith(page, marker, ORIGINAL);
    const explicitPrimary = await amountWith(page, marker, primary);
    expect(explicitPrimary, 'the seeded row did not convert at all').not.toBe(original);

    const noCookie = await amountWith(page, marker, null);
    expect(noCookie).toBe(explicitPrimary);
    // And the switcher agrees: the primary pill is the selected one.
    await expect(
      page.getByTestId('currency-switcher').getByRole('radio', { name: primary }),
    ).toHaveAttribute('aria-checked', 'true');
  });
});
