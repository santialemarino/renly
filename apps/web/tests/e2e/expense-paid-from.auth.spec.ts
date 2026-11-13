import {
  expect,
  request as playwrightRequest,
  test,
  type APIRequestContext,
  type Locator,
  type Page,
} from '@playwright/test';

import { API_BASE, apiToken } from './helpers/api';
import { testMarker } from './helpers/factories';
import { waitForHydration } from './helpers/hydration';

// Route literal mirrors apps/web/config/routes.ts, like every spec's.
const EXPENSES = '/expenses';
const QUICK_ADD_OPEN_MS = 20_000;
/*
 * The accounts are seeded in a currency no other spec writes, so "the one account of this type in this
 * currency" is true whatever the harness account already holds.
 */
const CURRENCY = 'BRL';

/*
 * "Paid from" on a new expense follows the payment method: cash from the cash account, debit or a
 * transfer from the bank account, a card from none. And the two doors into the form — the /expenses Add
 * button and the global quick-add — open it the same way: on today and the primary currency, with the
 * same account rule.
 */
test.describe('an expense’s "Paid from" follows its payment method (signed in)', () => {
  let api: APIRequestContext;
  let primary: string;
  const marker = testMarker('paid-from');
  const cashName = `${marker} Efectivo`;
  const bankName = `${marker} Banco`;
  const created: number[] = [];

  test.beforeAll(async () => {
    api = await playwrightRequest.newContext({
      baseURL: API_BASE,
      extraHTTPHeaders: { Authorization: `Bearer ${await apiToken()}` },
    });
    const settings = (await (await api.get('/settings')).json()) as {
      primary_currency: string | null;
    };
    primary = settings.primary_currency ?? 'ARS';
    for (const [name, type] of [
      [cashName, 'cash'],
      [bankName, 'bank'],
    ]) {
      const response = await api.post('/accounts', {
        data: {
          name,
          type,
          currency: CURRENCY,
          opening_balance: '0',
          opening_date: new Date().toISOString().slice(0, 10),
        },
      });
      expect(response.ok(), `POST /accounts: ${response.status()}`).toBe(true);
      created.push(((await response.json()) as { id: number }).id);
    }
  });

  test.afterAll(async () => {
    for (const id of created) await api.delete(`/accounts/${id}`);
    await api.dispose();
  });

  async function pick(page: Page, combobox: Locator, option: string | RegExp) {
    await combobox.click();
    await page.getByRole('option', { name: option }).first().click();
  }

  async function expectFollowsMethod(page: Page) {
    const dialog = page.getByRole('dialog');
    // Opened on today and the primary currency.
    await expect(dialog.getByTestId('expense-form-date')).not.toHaveText(/Select a date/);
    await expect(dialog.getByTestId('expense-form-currency')).toContainText(primary);

    await pick(page, dialog.getByTestId('expense-form-currency'), new RegExp(CURRENCY));
    const method = dialog.getByRole('combobox', { name: 'Payment method' });
    const paidFrom = dialog.getByRole('combobox', { name: 'Paid from' });
    // No method yet: nothing is guessed.
    await expect(paidFrom).not.toContainText(marker);

    await pick(page, method, 'Cash');
    await expect(paidFrom).toContainText(cashName);
    await pick(page, method, 'Debit');
    await expect(paidFrom).toContainText(bankName);
    await pick(page, method, 'Transfer');
    await expect(paidFrom).toContainText(bankName);
    // A card charge never names an account: the field goes, and so does the value.
    await pick(page, method, 'Credit Card');
    await expect(paidFrom).toHaveCount(0);
    await pick(page, method, 'Cash');
    await expect(paidFrom).toContainText(cashName);

    // A pick the user made is theirs: changing the method no longer moves it.
    await pick(page, paidFrom, 'None');
    await pick(page, method, 'Debit');
    await expect(paidFrom).not.toContainText(marker);

    await dialog.locator('[data-slot="dialog-close"]').click();
    await expect(dialog).toHaveCount(0);
  }

  test('from the /expenses Add button', async ({ page }) => {
    await page.goto(EXPENSES);
    const add = page.getByTestId('entity-list-add');
    await waitForHydration(add);
    await add.click();
    await expect(page.getByTestId('expense-form-notes')).toBeVisible();
    await expectFollowsMethod(page);
  });

  test('from the quick-add', async ({ page }) => {
    await page.goto(EXPENSES);
    const quickAdd = page.getByTestId('quick-add-trigger');
    await waitForHydration(quickAdd);
    await quickAdd.click();
    await expect(page.getByTestId('expense-form-notes')).toBeVisible({
      timeout: QUICK_ADD_OPEN_MS,
    });
    await expectFollowsMethod(page);
  });
});
