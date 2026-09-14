import { expect, test, type APIRequestContext } from '@playwright/test';

import { e2eCredentials } from './helpers/auth';

/*
 * The dashboard's two conversion frames, and the one assertion that can only be made end to end.
 *
 * The net-worth HEADLINE converts every term at today's rate; every point on the evolution CHART
 * converts at its own month's rate. Those are different questions and both answers are right — but
 * the last point's month ends on or after today, so the two must land on the same figure. That
 * agreement is what this unit built, and it rests on three things no stubbed test can exercise
 * together: the real `RateLookup` over the rates actually stored, the grid genuinely ending at the
 * current month in the user's timezone, and both endpoints reading the same card sources. The API
 * unit suite pins each piece against a fixed rate map; only a run against a live account with live
 * rates proves the pieces agree in the world.
 *
 * So the first test talks to the API rather than the DOM, deliberately: the chart abbreviates every
 * number it draws (the tooltip on a 4.5M point reads "4.5M"), so the browser cannot see the cent this
 * assertion is about. What the browser CAN see is the second test's subject — which hint the reader is
 * shown, and when.
 *
 * NOT covered, stated rather than implied: the historical points' values. Restating them is the change
 * this unit made, and a spec that asserted them would either recompute the service's arithmetic or
 * freeze one account's real history into a literal. Those are pinned in
 * `tests/unit/test_dashboard.py`, against a lookup whose rate moves per month.
 */

// Where the API is, for the one assertion the DOM cannot make. A shell var like E2E_EMAIL and
// E2E_PASSWORD — Playwright reads no dotenv file, so it stays out of `.env.example` too — with the
// local default that makes it optional. `||` rather than `??` so an empty value falls back.
// eslint-disable-next-line turbo/no-undeclared-env-vars
const API_BASE = process.env.E2E_API_URL || 'http://localhost:8000';

interface DashboardTotals {
  cardBalance: string;
  netWorth: string;
}

// Logs into the API directly for its own bearer token. The browser's session is a NextAuth cookie on
// the WEB origin, which the API never sees — so a request context cannot borrow it, and the harness
// credentials are the only way in.
async function apiToken(request: APIRequestContext): Promise<string> {
  const credentials = e2eCredentials();
  // The authenticated project only exists when both are set, so this cannot be null here — the check
  // is what makes that a type fact rather than a comment.
  if (credentials === null) throw new Error('E2E_EMAIL / E2E_PASSWORD are required for this spec');
  const response = await request.post(`${API_BASE}/auth/login`, { data: credentials });
  expect(response.ok(), `login to ${API_BASE} failed with ${response.status()}`).toBe(true);
  return (await response.json()).access_token;
}

// The headline and the chart's last point, both in the same display currency.
async function readTotals(
  request: APIRequestContext,
  token: string,
  currency: string,
): Promise<{ headline: DashboardTotals; lastPoint: DashboardTotals }> {
  const headers = { Authorization: `Bearer ${token}` };
  const overview = await request.get(`${API_BASE}/dashboard/overview?currency=${currency}`, {
    headers,
  });
  const evolution = await request.get(`${API_BASE}/dashboard/evolution?currency=${currency}`, {
    headers,
  });
  expect(overview.ok()).toBe(true);
  expect(evolution.ok()).toBe(true);
  const overviewBody = await overview.json();
  const points = (await evolution.json()).points;
  expect(points.length, 'the account has no evolution points to reconcile against').toBeGreaterThan(
    0,
  );
  const last = points[points.length - 1];
  return {
    headline: {
      cardBalance: overviewBody.credit_card_balance,
      netWorth: overviewBody.net_worth,
    },
    lastPoint: { cardBalance: last.card_balance, netWorth: last.net_worth },
  };
}

test.describe('the dashboard’s conversion basis (signed in)', () => {
  test('the chart’s last point agrees with the headline, at the rates actually stored', async ({
    request,
  }) => {
    const token = await apiToken(request);

    /*
     * Both currencies, because the gap this closed had a DIFFERENT SIGN in each. Measured on the real
     * account before the change: viewed in ARS the chart understated the card debt by 5,346 (old
     * dollar charges frozen at the month they landed, when the peso was stronger); viewed in USD it
     * OVERSTATED it by 20.24, the same charges read the other way round. A spec that checked one
     * currency would have passed on half of the defect.
     */
    for (const currency of ['ARS', 'USD']) {
      const { headline, lastPoint } = await readTotals(request, token, currency);
      // String equality on the serialised decimals, not a numeric tolerance: the whole point is that
      // the two agree to the cent, and a tolerance would accept the rounding drift that converting at
      // the wrong granularity produces.
      expect(lastPoint.cardBalance, `card balance in ${currency}`).toBe(headline.cardBalance);
      expect(lastPoint.netWorth, `net worth in ${currency}`).toBe(headline.netWorth);
    }
  });

  test('the conversion hint is shown only while a display currency is active', async ({ page }) => {
    // A cold `.next` compiles `/dashboard` on first request, and the budget that expires first is the
    // test's rather than any one navigation's.
    test.setTimeout(120_000);

    await page.goto('/dashboard');
    /*
     * This hint is dismissable forever, and the harness runs as a REAL account that may have dismissed
     * it months ago. Clearing the key is what makes the assertion about `show` rather than about one
     * account's history — without it the test would pass by rendering nothing at all.
     */
    await page.evaluate(() => localStorage.removeItem('currency-hint-dismissed'));

    const switcher = page.getByTestId('currency-switcher');
    await expect(switcher).toBeVisible({ timeout: 30_000 });

    // "Original" is the one selection where nothing converts, so the sentence about which rate is used
    // has nothing to explain and the page withholds it.
    const hint = page.getByTestId('hint-currency-hint-dismissed');
    await switcher.getByRole('radio', { name: 'X', exact: true }).click();
    await expect(hint).toBeHidden();

    // Any real currency converts, so the hint returns. Asserting the SENTENCE and not merely the
    // element: this unit rewrote it because the old one described a basis the dashboard stopped using,
    // and an element-only assertion would pass on the copy it was written to replace.
    await switcher.getByRole('radio', { name: 'ARS', exact: true }).click();
    await expect(hint).toBeVisible();
    await expect(hint).toContainText('the exchange rate that was in force then');
  });
});
