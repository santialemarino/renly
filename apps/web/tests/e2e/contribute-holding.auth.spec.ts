import { expect, test } from '@playwright/test';

// Route literals mirror apps/web/config/routes.ts. Kept local so the spec stays self-contained and
// free of build-time path-alias resolution under Playwright's loader.
const SHARED = '/shared';
const DASHBOARD = '/dashboard';

/*
 * A pot id no account can reach. Any positive integer works: the pot page and every flow under it
 * answer NotFound identically for "does not exist" and "you may not see it", which is the property
 * being asserted — an id cannot be probed to learn which pots exist.
 */
const UNREACHABLE_POT = 999999;

/*
 * The contribution flow's ROUTE GUARDS, which is the half of it this harness can reach.
 *
 * The harness account belongs to no group, so there is no divided pot to contribute to and no way to
 * drive the flow itself without first building a group, a pot and an agreed split through the UI —
 * a setup whose failures would be about the accounts and groups forms rather than about this flow.
 * Santi's call was to cover the guards here and add the round trip once the harness has a shared-data
 * fixture that several specs can share. Stated rather than implied: **the wizard's own steps are not
 * covered by any automated browser test.** What does cover them is 32 API unit tests, five
 * integration tests driving the real service against a real Postgres — including the invariant that
 * nobody else's share value moves, proven to go red when the pricing and the move are swapped — and a
 * two-account live walk in both locales.
 *
 * What IS worth pinning here is the thing those cannot see: that the flow is unreachable by URL for
 * an account with no claim on the pot. It is a write flow end to end, so it has no read-only view to
 * fall back on — every one of its four routes answers the app's own 404 instead, exactly as /admin
 * does for a non-admin.
 */
test.describe('contribute-a-holding route guards (signed in)', () => {
  test('the flow is unreachable for a pot the account cannot write', async ({ page }) => {
    await page.goto(`/shared/pots/${UNREACHABLE_POT}/contribute`);

    /*
     * The app's own not-found page rather than a redirect to /login: the session is valid, so this is
     * a 404 about the POT. Asserting the testid rather than the copy keeps it locale-independent —
     * the run's language is whatever the stored session carries.
     */
    await expect(page.getByTestId('not-found')).toBeVisible();
  });

  test('and so are the three flows beside it, for the same pot', async ({ page }) => {
    /*
     * The counterweight, and the reason this test exists rather than trusting the one above: a guard
     * that answered 404 for every URL under /shared would pass that test while proving nothing. These
     * three are the established behaviour, so agreeing with them is what makes the new route's answer
     * meaningful — and if one of them ever stops agreeing, the divergence is the finding.
     */
    for (const flow of ['take-out', 'buy-out', 'contribute']) {
      await page.goto(`/shared/pots/${UNREACHABLE_POT}/${flow}`);
      await expect(page.getByTestId('not-found'), `/${flow} should not be reachable`).toBeVisible();
    }
  });

  test('a reachable page under the same session still renders, so the 404s are about the pot', async ({
    page,
  }) => {
    // Without this the two tests above would also pass on a broken session, since a sessionless
    // visitor is bounced to /login and never sees the not-found page at all.
    await page.goto(SHARED);
    await expect(page).toHaveURL(new RegExp(`${SHARED}$`));
    await expect(page.getByTestId('not-found')).toHaveCount(0);

    await page.goto(DASHBOARD);
    await expect(page.getByTestId('quick-add-trigger')).toBeVisible();
  });
});
