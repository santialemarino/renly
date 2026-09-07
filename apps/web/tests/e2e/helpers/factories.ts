import { expect, type Page } from '@playwright/test';

// Route literals mirror apps/web/config/routes.ts. Kept local like every spec's — the Playwright
// loader resolves no build-time path aliases.
const EXPENSES = '/expenses';

/*
 * Factories for the authenticated specs.
 *
 * Every authenticated spec runs against a real account with real history, so a spec must never assume
 * a starting state and must never depend on a row somebody else created. The pattern here is what
 * makes that work: each factory returns a MARKER — a string unique to this run — and every assertion
 * and cleanup is scoped to the row carrying it. Two consequences worth stating, because they are what
 * a later factory has to preserve:
 *
 *   * the marker goes in a free-text field, so it survives the round trip through the API and comes
 *     back on the list page as something a locator can find, with no id to thread through;
 *   * cleanup is driven through the same UI a user would use, so a spec that fails mid-flow leaves at
 *     most one identifiable row behind rather than a mystery.
 */

// A value unique to this run, so a spec never matches a row another run (or a real user) created.
export function testMarker(label: string): string {
  return `e2e-${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

// The row on /expenses carrying this marker in its notes. A locator, so it auto-waits and can be
// asserted absent as easily as present.
export function expenseRow(page: Page, marker: string) {
  return page.getByRole('row').filter({ hasText: marker });
}

/*
 * Creates an expense through the global quick-add, which is the fastest real path to one from
 * anywhere in the app, and returns nothing the caller has to remember — the marker is the handle.
 *
 * Only the amount and the notes are typed. Everything else the form needs is pre-filled by the
 * quick-add itself (today's date, the primary currency, the sole eligible account when there is one),
 * which is precisely the behaviour worth pinning: a spec that filled every field would still pass if
 * the pre-fill stopped working.
 */
export async function createExpenseViaQuickAdd(page: Page, marker: string, amount: string) {
  await page.getByTestId('quick-add-trigger').click();
  const notes = page.getByTestId('expense-form-notes');
  await expect(notes).toBeVisible();

  await page.getByTestId('expense-form-amount').fill(amount);
  await notes.fill(marker);
  await page.getByTestId('expense-form-submit').click();

  // The dialog closing is the save's own acknowledgement — the submit handler closes it only after
  // the action resolves, so waiting on this is waiting on the write rather than on a timer.
  await expect(notes).toBeHidden();
}

/*
 * Deletes the expense carrying this marker, through the row's own delete action and its confirmation.
 * Safe to call when the row is already gone, so it can sit in a `finally` without knowing whether the
 * test that just ran got as far as creating anything.
 *
 * It NEVER throws, and that is the load-bearing part: a cleanup called from a `finally` that raises
 * replaces the assertion error that actually failed the test with its own, so the real cause vanishes.
 * A cleanup that could not run is reported and moves on — the marker is unique per run, so the worst
 * case is one identifiable leftover row rather than a lost diagnosis.
 */
export async function deleteExpenseByMarker(page: Page, marker: string) {
  try {
    await page.goto(EXPENSES);
    const row = expenseRow(page, marker);
    if ((await row.count()) === 0) return;

    await row.first().getByTestId('expense-delete').click();
    await page.getByTestId('confirm-dialog-confirm').click();
    await expect(expenseRow(page, marker)).toHaveCount(0);
  } catch (error) {
    console.warn(`e2e cleanup could not remove the expense marked ${marker}:`, error);
  }
}
