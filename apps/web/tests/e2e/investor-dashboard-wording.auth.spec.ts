import {
  expect,
  request as playwrightRequest,
  test,
  type APIRequestContext,
} from '@playwright/test';

import { API_BASE, apiToken } from './helpers/api';
import { testMarker } from './helpers/factories';

// Route literal mirrors apps/web/config/routes.ts, like every spec's.
const INVESTOR_DASHBOARD = '/investor-dashboard';

/*
 * Two pieces of wording on the investor dashboard, in both languages: the per-holding change column is
 * "This month" (a bare "Month" read as a date), and the by-collection view notes that the collections
 * can overlap, since an investment can sit in more than one.
 */
const COPY = {
  en: { column: 'This month', byCollection: 'By collection', note: /more than one collection/ },
  es: { column: 'Este mes', byCollection: 'Por colección', note: /más de una colección/ },
} as const;

test.describe('investor dashboard wording (signed in)', () => {
  let api: APIRequestContext;
  let investmentId: number;

  test.beforeAll(async () => {
    api = await playwrightRequest.newContext({
      baseURL: API_BASE,
      extraHTTPHeaders: { Authorization: `Bearer ${await apiToken()}` },
    });
    // A valued holding, so the table and the distribution have something to show.
    const created = await api.post('/investments', {
      data: { name: testMarker('wording'), category: 'stocks', base_currency: 'USD' },
    });
    expect(created.ok(), `POST /investments: ${created.status()}`).toBe(true);
    investmentId = ((await created.json()) as { id: number }).id;
    const snapshot = await api.post(`/investments/${investmentId}/snapshots`, {
      data: { date: new Date().toISOString().slice(0, 10), value: '100', currency: 'USD' },
    });
    expect(snapshot.ok(), `POST snapshot: ${snapshot.status()}`).toBe(true);
  });

  test.afterAll(async () => {
    await api.patch(`/investments/${investmentId}/archive`);
    await api.dispose();
  });

  for (const locale of ['en', 'es'] as const) {
    test(`reads right in ${locale}`, async ({ page }) => {
      await page
        .context()
        .addCookies([{ name: 'NEXT_LOCALE', value: locale, domain: 'localhost', path: '/' }]);
      await page.goto(INVESTOR_DASHBOARD);
      await expect(
        page.getByRole('columnheader', { name: COPY[locale].column, exact: true }),
      ).toBeVisible();

      await expect(page.getByTestId('collection-overlap-note')).toHaveCount(0);
      await page.getByRole('radio', { name: COPY[locale].byCollection }).click();
      await expect(page.getByTestId('collection-overlap-note')).toHaveText(COPY[locale].note);
    });
  }
});
