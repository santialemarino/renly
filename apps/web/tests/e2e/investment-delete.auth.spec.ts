import {
  expect,
  request as playwrightRequest,
  test,
  type APIRequestContext,
} from '@playwright/test';

import { API_BASE, apiToken } from './helpers/api';
import { testMarker } from './helpers/factories';
import { waitForHydration } from './helpers/hydration';

// Route literal mirrors apps/web/config/routes.ts, like every spec's.
const INVESTMENTS = '/investments';

/*
 * Deleting an investment. One with no history (no snapshot, no transaction) offers Delete behind a
 * type-to-confirm; one with history offers only Archive, whose name says why; and an archived row,
 * shown under "Show archived", says it is archived in words beside its name.
 */
test.describe('deleting an investment (signed in)', () => {
  let api: APIRequestContext;
  const created: number[] = [];

  async function seedInvestment(name: string): Promise<number> {
    const response = await api.post('/investments', {
      data: { name, category: 'stocks', base_currency: 'USD' },
    });
    expect(response.ok(), `POST /investments: ${response.status()}`).toBe(true);
    const { id } = (await response.json()) as { id: number };
    created.push(id);
    return id;
  }

  test.beforeAll(async () => {
    api = await playwrightRequest.newContext({
      baseURL: API_BASE,
      extraHTTPHeaders: { Authorization: `Bearer ${await apiToken()}` },
    });
  });

  test.afterAll(async () => {
    // A history row cannot be deleted through the API either; archiving is all that is left, and a
    // marker keeps it out of every other spec's way.
    for (const id of created) {
      const deleted = await api.delete(`/investments/${id}`);
      if (!deleted.ok()) await api.patch(`/investments/${id}/archive`);
    }
    await api.dispose();
  });

  test('an investment with no history is deleted after typing its name', async ({ page }) => {
    const name = testMarker('inv-delete');
    const id = await seedInvestment(name);

    await page.goto(`${INVESTMENTS}?search=${encodeURIComponent(name)}`);
    const row = page.getByRole('row').filter({ hasText: name });
    await expect(row).toBeVisible();
    await expect(row.getByTestId('investment-archive')).toHaveCount(0);
    const remove = row.getByTestId('investment-delete');
    await waitForHydration(remove);
    await remove.click();

    const dialog = page.getByRole('dialog');
    await dialog.locator('input#type-to-confirm').fill(name);
    await dialog.locator('[data-slot="dialog-footer"] button').last().click();

    await expect(dialog).toHaveCount(0);
    await expect(row).toHaveCount(0);
    expect((await api.get(`/investments/${id}`)).status()).toBe(404);
  });

  test('an investment with history can only be archived, and says why', async ({ page }) => {
    const name = testMarker('inv-history');
    const id = await seedInvestment(name);
    const snapshot = await api.post(`/investments/${id}/snapshots`, {
      data: { date: new Date().toISOString().slice(0, 10), value: '100', currency: 'USD' },
    });
    expect(snapshot.ok(), `POST snapshot: ${snapshot.status()}`).toBe(true);
    // The API refuses too, whatever the UI offers.
    const refused = await api.delete(`/investments/${id}`);
    expect(refused.status()).toBe(409);
    expect(((await refused.json()) as { code: string }).code).toBe('investment_has_history');

    await page.goto(`${INVESTMENTS}?search=${encodeURIComponent(name)}`);
    const row = page.getByRole('row').filter({ hasText: name });
    await expect(row).toBeVisible();
    await expect(row.getByTestId('investment-delete')).toHaveCount(0);
    await expect(row.getByTestId('investment-archive')).toHaveAccessibleName(/can't be deleted/);
    await expect(row.getByTestId('investment-archived-badge')).toHaveCount(0);

    // Archived, and listed under "Show archived": the row says so beside the name.
    expect((await api.patch(`/investments/${id}/archive`)).ok()).toBe(true);
    await page.goto(`${INVESTMENTS}?search=${encodeURIComponent(name)}&show_archived=true`);
    await expect(row.getByTestId('investment-archived-badge')).toHaveText('Archived');
    await expect(row).toHaveAttribute('data-archived', 'true');
  });
});
