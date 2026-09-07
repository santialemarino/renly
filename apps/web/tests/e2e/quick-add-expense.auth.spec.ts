import { expect, test } from '@playwright/test';

import {
  createExpenseViaQuickAdd,
  deleteExpenseByMarker,
  expenseRow,
  testMarker,
} from './helpers/factories';

// Route literals mirror apps/web/config/routes.ts. Kept local so the spec stays self-contained and
// free of build-time path-alias resolution under Playwright's loader.
const DASHBOARD = '/dashboard';
const EXPENSES = '/expenses';
const SNAPSHOTS = '/snapshots';

/*
 * How long the table may take to stop showing a deleted row.
 *
 * Longer than the 5s `expect` default on purpose, and the number is measured rather than padded: the
 * delete finishes in the database immediately, but what removes the row from the rendered table is a
 * `router.refresh()`, and a dev server compiling `/expenses` for the first time inside this test does
 * not land it inside five seconds. Same test, same tree: 6.7s run alone against a warm server, 12.0s
 * inside the full suite, and past the default on the first run after a server start — which made this
 * spec fail roughly every other cold run and pass on every retry, the worst kind of red.
 *
 * It buys patience, not tolerance: the assertion still has to become true, and the reload below
 * re-reads from the server so a row that only LOOKED gone would still fail.
 */
const ROW_GONE_MS = 20_000;

// Any valid amount; the row is found by its marker rather than this figure, because the rendered
// value is locale-formatted and the run's locale is whatever the stored session carries.
const EXPENSE_AMOUNT = '1234.56';

/*
 * The repo's first AUTHENTICATED spec, and the one that bootstraps the harness: a session from
 * globalSetup, a factory that writes through a real form, and a cleanup that removes what it wrote.
 * Everything after it can assume all three.
 *
 * It drives the global quick-add because that is the one entry point reachable from every protected
 * route, which is what lets the round trip start on a page that has nothing to do with expenses — and
 * because the pre-fill it exercises (today's date, the primary currency, the single eligible account)
 * is invisible to every other kind of test: the form's rules live in `lib/` and are unit-tested there,
 * but whether the trigger actually hands them the right values only shows in a browser.
 *
 * The write and the delete are ONE test rather than two, deliberately. Split across tests the second
 * would depend on the first having run — which the config's single worker happens to guarantee today
 * and no spec should rely on. A round trip is one fact anyway: the row appeared, and then it did not.
 */
test.describe('quick-add expense round trip (signed in)', () => {
  test('the session from globalSetup reaches a protected route', async ({ page }) => {
    await page.goto(DASHBOARD);

    // The assertion that matters is the ABSENCE of a bounce: the proxy gate sends a sessionless
    // visitor to /login, so staying on /dashboard is the whole proof that the stored state works.
    await expect(page).toHaveURL(new RegExp(`${DASHBOARD}$`));
    await expect(page.getByTestId('quick-add-trigger')).toBeVisible();
  });

  test('an expense added from anywhere reaches the list, and can be deleted from it', async ({
    page,
  }) => {
    const marker = testMarker('quick-add-expense');

    try {
      // Deliberately NOT /expenses: the quick-add's reason to exist is being reachable from anywhere,
      // and starting on the expenses page would prove only that its own toolbar works.
      await page.goto(SNAPSHOTS);
      await expect(page.getByTestId('quick-add-trigger')).toBeVisible();

      await createExpenseViaQuickAdd(page, marker, EXPENSE_AMOUNT);

      await page.goto(EXPENSES);
      const row = expenseRow(page, marker);
      await expect(row).toHaveCount(1);

      await row.first().getByTestId('expense-delete').click();
      await page.getByTestId('confirm-dialog-confirm').click();
      await expect(expenseRow(page, marker)).toHaveCount(0, { timeout: ROW_GONE_MS });

      // Gone from the server, not only from the rendered table — a reload re-reads the list.
      await page.reload();
      await expect(expenseRow(page, marker)).toHaveCount(0);
    } finally {
      /*
       * The account is real and has real history, so a failure anywhere above must not leave an e2e
       * row in it for the next run to trip over. `finally` rather than an `afterEach` hook because the
       * marker is local to this test, and the helper is a no-op when the row is already gone — which
       * is the normal case, since the test deletes it itself.
       */
      await deleteExpenseByMarker(page, marker);
    }
  });
});
