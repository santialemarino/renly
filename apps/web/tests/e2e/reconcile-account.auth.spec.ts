import { expect, test } from '@playwright/test';

import { accountRow, createAccount, deleteAccountByMarker, testMarker } from './helpers/factories';

/*
 * A reconciliation's full round trip, on a PRIVATE account.
 *
 * Why the private one. This unit is about a POT's account, and a shared reconciliation is by
 * construction a statement about money several people co-own: showing one needs a group, a divided
 * pot and an account that pot holds. The harness account belongs to no group, so the blocker is the
 * SHARED-DATA fixture rather than a second login — a second session with nothing in common with the
 * first still cannot show a shared reconciliation. That fixture now has THREE specs waiting on it
 * (this one, the re-agreement confirmation from PR 13 and the contribution flow from PR 12), which is
 * the case for building it as its own unit rather than a third time inside a feature PR.
 *
 * What makes the private path worth a spec anyway is that this unit MOVED it. Reconciling now resolves
 * its account through `get_account_in_scope` rather than the private-only lookup, takes a row lock
 * before reading the balance, and posts its adjustment through a branch that did not exist before. A
 * private account exercises every one of those and asserts the behaviour that must not have changed.
 *
 * ONE test rather than several, and deliberately. The date guards — future, before the account opened,
 * before the latest reconciliation — are each an API refusal restated as a disabled day in the picker,
 * and every browser assertion about a disabled DAY is conditional on that day being in the rendered
 * month. A conditional assertion is a test that can pass without running, so those stay where they can
 * be stated unconditionally: fifteen API unit tests drive all three, in both directions.
 *
 * Stated rather than implied: **no automated browser test exercises reconciling a SHARED account.**
 * What does cover it is 37 API unit tests and 19 integration tests driving the real policies, grants and
 * CHECK constraints against a real Postgres — including the read-only co-owner's insert and delete, the
 * column grant, and both derivations of the balance over a pot's account holding a row from every
 * source that can reach one — plus a two-account live walk in both locales.
 */
test.describe('reconciling an account (signed in)', () => {
  test('records the difference, shows it in the history, and undoes it on delete', async ({
    page,
  }) => {
    /*
     * A per-TEST budget, for the reason PR 13's spec documents at length: on a cold `.next` the first
     * compile of a route is measured in tens of seconds, and the budget that expires first is
     * Playwright's for the test as a whole rather than any single navigation's. This spec loads
     * `/accounts` and drives three dialogs on it, so it pays that route's first compile once.
     */
    test.setTimeout(120_000);

    const marker = testMarker('recon');
    try {
      await createAccount(page, marker, '1000');

      const row = accountRow(page, marker);
      await expect(row).toBeVisible();
      // The opening figure IS the derived balance on an account nothing has moved, so this is the
      // starting point every assertion below is measured against.
      await expect(row).toContainText('1,000');

      // Reconcile to a REAL balance below the derived one, so the adjustment is an expense and the
      // direction is visible rather than inferred.
      await row.getByTestId('account-reconcile').click();
      const balance = page.getByTestId('account-reconcile-balance');
      await expect(balance).toBeVisible({ timeout: 20_000 });
      await balance.fill('940');
      await page.getByTestId('account-reconcile-submit').click();
      // The dialog closing is the save's own acknowledgement: the submit handler closes it only after
      // the action resolves, so waiting on this waits on the write rather than on a timer.
      await expect(balance).toBeHidden();

      /*
       * The whole point of a reconciliation, asserted on the row the user actually reads: the balance
       * is now the figure they typed, because the adjustment closed the gap. Asserting only that the
       * reconciliation row exists would pass even if the adjustment were never posted — which is
       * precisely the failure mode a shared adjustment in the wrong table produces.
       */
      await expect(row).toContainText('940');

      // Expanding the row opens its reconciliation history, which is the surface this unit made
      // shared-readable and which a private account has always had.
      await row.click();
      const panel = page.getByRole('row').filter({ hasText: 'Never reconciled' });
      await expect(panel).toHaveCount(0);
      await expect(page.getByTestId('reconciliation-delete')).toBeVisible();

      /*
       * The escape hatch for a mistyped balance: deleting the reconciliation cascade-drops the
       * adjustment it created, so the balance returns to what it was. This is the assertion that
       * proves the link is a real ON DELETE CASCADE rather than a row that merely stopped being
       * listed — the derived balance has no memory of its own.
       */
      await page.getByTestId('reconciliation-delete').click();
      await page.getByTestId('confirm-dialog-confirm').click();
      /*
       * Wait for the delete to be ACKNOWLEDGED before re-reading. The history panel drops the row only
       * after the request resolves, so its disappearance is the write's own receipt — without it the
       * reload below races the DELETE and can re-render the page from before it landed, which is
       * exactly how this spec failed on a loaded machine while the API was provably correct.
       */
      await expect(page.getByTestId('reconciliation-delete')).toHaveCount(0);
      /*
       * Then re-read from the server rather than waiting on the page to catch up. The panel refreshes
       * itself, but the ROW's balance comes from the page's server component, so it changes only once
       * `router.refresh()` lands — and asserting on that window is asserting on a race. Reloading
       * makes the assertion what it should be about: what the database now holds.
       */
      await page.reload();
      await expect(accountRow(page, marker)).toContainText('1,000');
    } finally {
      await deleteAccountByMarker(page, marker);
    }
  });
});
