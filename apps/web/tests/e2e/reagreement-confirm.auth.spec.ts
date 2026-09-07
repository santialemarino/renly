import { expect, test } from '@playwright/test';

// Route literals mirror apps/web/config/routes.ts. Kept local so the spec stays self-contained and
// free of build-time path-alias resolution under Playwright's loader.
const SHARED = '/shared';
const DASHBOARD = '/dashboard';

/*
 * A pot id no account can reach. Any positive integer works: the pot page answers NotFound identically
 * for "does not exist" and "you may not see it", which is the property being asserted — an id cannot be
 * probed to learn which pots exist.
 */
const UNREACHABLE_POT = 999999;

/*
 * The ownership ledger's REACHABILITY, which is the half of the confirmation this harness can reach.
 *
 * Why not the round trip. A confirmation is a statement about what somebody ELSE did — the affected
 * seat is by construction never the seat that recorded the change — so demonstrating one needs two
 * authenticated sessions that share a group, a divided pot and a re-agreement between them. The harness
 * account belongs to no group, so the blocker is the SHARED-DATA fixture rather than the second login:
 * a second session with nothing in common with the first still cannot show a confirmation. Building the
 * shared data through the UI means a group, a name-only member, a pot, a holding moved in, an agreed
 * opening and a re-agreement — eight dialogs whose failures would each report as a confirmation
 * failure. Santi's call on PR 12 was guard-level now and the round trip once that fixture exists, and
 * this unit is in the same position.
 *
 * Stated rather than implied: **no automated browser test exercises confirming or un-confirming.** What
 * does cover them is 30 API unit tests, 18 integration tests driving the real policies and grants
 * against a real Postgres — including the affected-seat expression in every direction, the column grant
 * and the lock on both DELETE policies — and a two-account live walk in both locales.
 *
 * What IS worth pinning here is the thing those cannot see: the ledger, and therefore both row actions,
 * live on the pot page, and that page is unreachable by URL for an account with no claim on the pot. The
 * actions themselves are gated on flags the API resolves per row, so an unreachable page is the only
 * client-side gate there is.
 */
test.describe('ownership-ledger reachability (signed in)', () => {
  test('the pot page is unreachable for a pot the account cannot see', async ({ page }) => {
    await page.goto(`/shared/pots/${UNREACHABLE_POT}`);

    /*
     * The app's own not-found page rather than a redirect to /login: the session is valid, so this is a
     * 404 about the POT. Asserting the testid rather than the copy keeps it locale-independent — the
     * run's language is whatever the stored session carries.
     */
    await expect(page.getByTestId('not-found')).toBeVisible();
    // And no ledger control leaked onto the 404, which is what would happen if the page rendered its
    // sections before resolving the pot.
    await expect(page.getByTestId('ledger-confirm')).toHaveCount(0);
    await expect(page.getByTestId('ledger-unconfirm')).toHaveCount(0);
    await expect(page.getByTestId('ledger-delete')).toHaveCount(0);
  });

  test('a reachable page under the same session still renders, so the 404 is about the pot', async ({
    page,
  }) => {
    // Without this the test above would also pass on a broken session, since a sessionless visitor is
    // bounced to /login and never sees the not-found page at all.
    await page.goto(SHARED);
    await expect(page).toHaveURL(new RegExp(`${SHARED}$`));
    await expect(page.getByTestId('not-found')).toHaveCount(0);

    await page.goto(DASHBOARD);
    await expect(page.getByTestId('quick-add-trigger')).toBeVisible();
  });
});
