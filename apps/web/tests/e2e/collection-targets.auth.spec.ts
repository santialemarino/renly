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
const COLLECTIONS = '/collections';

/*
 * Collection targets adding up to more than 100% are WARNED about, never refused: in the form while a
 * value would take the sum over, and on the collections page while the saved targets are over.
 */
test.describe('collection targets over 100% (signed in)', () => {
  let api: APIRequestContext;
  const created: number[] = [];

  async function seedCollection(name: string, target: number): Promise<void> {
    const response = await api.post('/collections', {
      data: { name, target_percentage: target },
    });
    expect(response.ok(), `POST /collections: ${response.status()}`).toBe(true);
    created.push(((await response.json()) as { id: number }).id);
  }

  test.beforeAll(async () => {
    api = await playwrightRequest.newContext({
      baseURL: API_BASE,
      extraHTTPHeaders: { Authorization: `Bearer ${await apiToken()}` },
    });
  });

  test.afterAll(async () => {
    for (const id of created) await api.delete(`/collections/${id}`);
    await api.dispose();
  });

  test('warns in the form and on the page, and still saves', async ({ page }) => {
    // The page's warning sums EVERY collection, so start from what the account already has.
    const existing = (await (await api.get('/collections')).json()) as {
      target_percentage: string | null;
    }[];
    const already = existing.reduce((sum, c) => sum + Number(c.target_percentage ?? 0), 0);
    test.skip(already > 60, 'the harness account already holds most of the 100%');
    const marker = testMarker('targets');
    await seedCollection(`${marker} A`, 60 - already);

    await page.goto(COLLECTIONS);
    await expect(page.getByTestId('collection-targets-over')).toHaveCount(0);

    const add = page.getByTestId('entity-list-add');
    await waitForHydration(add);
    await add.click();
    const dialog = page.getByRole('dialog');
    await dialog.locator('input[name="name"]').fill(`${marker} B`);
    const target = dialog.locator('input[name="targetPercentage"]');
    await target.click();
    await page.keyboard.type('30');
    await expect(dialog.getByTestId('collection-form-targets-over')).toHaveCount(0);
    await page.keyboard.press('ControlOrMeta+A');
    await page.keyboard.type('45'); // 60 + 45 = 105: over, and saved anyway.
    await expect(dialog.getByTestId('collection-form-targets-over')).toBeVisible();
    await dialog.locator('button[type="submit"]').click();
    await expect(dialog).toHaveCount(0);

    await expect(page.getByTestId('collection-targets-over')).toBeVisible();
    await expect(page.getByTestId('collection-targets-over')).toContainText('105');
    const listed = (await (await api.get('/collections')).json()) as { id: number; name: string }[];
    created.push(...listed.filter((c) => c.name === `${marker} B`).map((c) => c.id));
    expect(created).toHaveLength(2);
  });
});
