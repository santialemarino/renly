import { expect, test, type Route } from '@playwright/test';

import { accountRow, createAccount, deleteAccountByMarker, testMarker } from './helpers/factories';

/*
 * Where keyboard focus goes when an expandable row's paged list is retried. The Retry unmounts the
 * moment it is pressed — the panel swaps its line for the loading line, and fades between them — so
 * focus has to be handed somewhere on purpose or it falls to the body and the next Tab starts from the
 * top of the page. It waits on the list, comes back to the new Retry when the load fails again, and
 * stays on the list once it lands.
 *
 * The failure is made in the browser: the panel reads its history through a Server Action, which is a
 * POST to the page carrying a `Next-Action` header, and those are failed while the route is held.
 */
test.describe('retrying a paged list (signed in)', () => {
  test('keeps focus in the panel through a failed retry and a successful one', async ({ page }) => {
    test.setTimeout(90_000);
    const marker = testMarker('pagedfocus');
    try {
      await createAccount(page, marker, '1000');
      const row = accountRow(page, marker);
      await expect(row).toBeVisible();

      const failActions = (route: Route) =>
        route.request().method() === 'POST' && route.request().headers()['next-action']
          ? route.fulfill({ status: 500, body: 'held' })
          : route.fallback();
      await page.route('**/accounts', failActions);

      await row.locator('button[aria-expanded]').click();
      // Both of the account's panels fail to load.
      const errors = page.getByTestId('paged-list-load-error');
      await expect(errors).toHaveCount(2);

      // A keyboard press on the first Retry, while the load still fails.
      await errors.first().getByRole('button').focus();
      await page.keyboard.press('Enter');
      // The pressed Retry is gone (its panel is loading again), then a new one is back.
      await expect(errors).toHaveCount(1);
      await expect(errors).toHaveCount(2);
      await expect(errors.first().getByRole('button')).toBeFocused();

      // Then a retry that lands: focus stays in the panel, on the list the rows come into.
      await page.unroute('**/accounts', failActions);
      await page.keyboard.press('Enter');
      await expect(errors).toHaveCount(1);
      await page.waitForTimeout(1000);
      await expect(errors).toHaveCount(1);
      const focused = page.locator(':focus');
      await expect(focused).toHaveAttribute('tabindex', '-1');
      expect(await focused.evaluate((element) => element.tagName)).toBe('DIV');
    } finally {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
      await deleteAccountByMarker(page, marker);
    }
  });
});
