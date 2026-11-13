import { expect, request as playwrightRequest, test } from '@playwright/test';

import { API_BASE, apiToken } from './helpers/api';
import { testMarker } from './helpers/factories';
import { waitForHydration } from './helpers/hydration';

// Route literal mirrors apps/web/config/routes.ts, like every spec's.
const ACCOUNT = '/account';

/*
 * Renaming yourself from /account: the field opens on the name the API has now, a save reaches the
 * API, and a reload shows the new name rather than the one the session was signed in with.
 */
test('the account name can be changed from /account (signed in)', async ({ page }) => {
  const api = await playwrightRequest.newContext({
    baseURL: API_BASE,
    extraHTTPHeaders: { Authorization: `Bearer ${await apiToken()}` },
  });
  const original = ((await (await api.get('/auth/me')).json()) as { name: string }).name;
  const renamed = testMarker('name');
  try {
    await page.goto(ACCOUNT);
    const input = page.getByTestId('account-name-input');
    await expect(input).toHaveValue(original);
    await waitForHydration(input);

    // Blank is refused in the form, before anything is sent.
    await input.fill('   ');
    await page.getByTestId('account-name-submit').click();
    await expect(page.getByText('This field is required')).toBeVisible();

    await input.fill(renamed);
    await page.getByTestId('account-name-submit').click();
    await expect
      .poll(async () => ((await (await api.get('/auth/me')).json()) as { name: string }).name)
      .toBe(renamed);

    await page.reload();
    await expect(page.getByTestId('account-name-input')).toHaveValue(renamed);
  } finally {
    await api.patch('/me', { data: { name: original } });
    await api.dispose();
  }
});
