import { expect, test, type APIRequestContext } from '@playwright/test';

import { API_BASE, apiToken } from './helpers/api';

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

interface DashboardTotals {
  cardBalance: string;
  netWorth: string;
}

// The account's own display currencies, in the order the sidebar offers them: primary first, then the
// optional secondary. "Original" is excluded — it converts nothing, so there is no agreement to check.
async function displayCurrencies(request: APIRequestContext, token: string): Promise<string[]> {
  const response = await request.get(`${API_BASE}/settings`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  const settings = await response.json();
  return [settings.primary_currency, settings.secondary_currency].filter(Boolean);
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
    const token = await apiToken();

    /*
     * TWO display currencies, because the gap this closed had a DIFFERENT SIGN in each. Measured on the
     * real account before the change: viewed in ARS the chart understated the card debt by 5,346 (old
     * dollar charges frozen at the month they landed, when the peso was stronger); viewed in USD it
     * OVERSTATED it by 20.24, the same charges read the other way round. A spec that checked one
     * currency would have passed on half of the defect. They are the harness account's own two, read
     * from Settings rather than hardcoded — the invariant is about ANY pair, and naming a pair would
     * make the spec fail on a differently-configured account for a reason that is not a defect.
     */
    const currencies = await displayCurrencies(request, token);
    expect(
      currencies.length,
      'the account needs a second display currency to check both signs',
    ).toBe(2);

    let anyCardDebt = false;
    for (const currency of currencies) {
      const { headline, lastPoint } = await readTotals(request, token, currency);
      anyCardDebt ||= Number(headline.cardBalance) !== 0;
      // String equality on the serialised decimals, not a numeric tolerance: the whole point is that
      // the two agree to the cent, and a tolerance would accept the rounding drift that converting at
      // the wrong granularity produces. SOFT, so a regression reports every currency it breaks rather
      // than stopping at the first — the two signs above are two findings, not one.
      expect.soft(lastPoint.cardBalance, `card balance in ${currency}`).toBe(headline.cardBalance);
      expect.soft(lastPoint.netWorth, `net worth in ${currency}`).toBe(headline.netWorth);
    }

    /*
     * An account with no card debt satisfies every assertion above with two zeros, which is a pass that
     * proves nothing — the defect this pins can only appear on a card that HAS an outstanding bucket.
     * Reported as a skip rather than swallowed, so a run against such an account says so out loud
     * instead of banking a green tick.
     */
    test.skip(
      !anyCardDebt,
      'the harness account carries no card balance, so there is nothing to reconcile',
    );
  });

  test('the investor chart’s last point is the portfolio headline, valued at today’s rate', async ({
    request,
  }) => {
    /*
     * What the portfolio holds now converts at today's rate, and every point of the evolution chart at
     * its own month's — a holding carried forward from an older snapshot included. The current month's
     * point therefore lands on the headline's own figure, and the chart runs on to the current month
     * even when the newest snapshot is older. Before, the carried holding kept its snapshot's rate and
     * the chart stopped at the snapshot's month, so the two drifted apart by whatever the currency did.
     *
     * So the account needs a holding valued in an EARLIER month, in a currency the display converts —
     * seeded here in the account's secondary currency, two months back. Investments can be archived but
     * never deleted, so it is one fixed-name row found again (and unarchived) by every run and archived
     * by its cleanup; archived holdings count nowhere.
     */
    const token = await apiToken();
    const headers = { Authorization: `Bearer ${token}` };
    const currencies = await displayCurrencies(request, token);
    const holdingName = 'e2e-conversion-basis-holding';
    const listed = await request.get(
      `${API_BASE}/investments?active_only=false&page_size=100&search=${holdingName}`,
      { headers },
    );
    expect(listed.ok()).toBe(true);
    let id = ((await listed.json()).items as { id: number; name: string }[]).find(
      (row) => row.name === holdingName,
    )?.id;
    if (id === undefined) {
      const created = await request.post(`${API_BASE}/investments`, {
        headers,
        data: { name: holdingName, category: 'cedears', base_currency: currencies[1] },
      });
      expect(created.ok(), `POST /investments: ${created.status()}`).toBe(true);
      id = (await created.json()).id as number;
    } else {
      const unarchived = await request.patch(`${API_BASE}/investments/${id}/unarchive`, {
        headers,
      });
      expect(unarchived.ok(), `PATCH unarchive: ${unarchived.status()}`).toBe(true);
    }
    try {
      const now = new Date();
      const valuedOn = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 2, 15));
      const snapshot = await request.post(`${API_BASE}/investments/${id}/snapshots`, {
        headers,
        data: {
          date: valuedOn.toISOString().slice(0, 10),
          value: '1234.56',
          currency: currencies[1],
        },
      });
      expect(snapshot.ok(), `POST snapshot: ${snapshot.status()}`).toBe(true);

      for (const currency of currencies) {
        const portfolio = await request.get(`${API_BASE}/metrics/portfolio?currency=${currency}`, {
          headers,
        });
        const evolution = await request.get(
          `${API_BASE}/metrics/portfolio/evolution?currency=${currency}`,
          { headers },
        );
        expect(portfolio.ok()).toBe(true);
        expect(evolution.ok()).toBe(true);
        const points = (await evolution.json()).points as { date: string; total_value: string }[];
        expect(points.length, `portfolio evolution in ${currency}`).toBeGreaterThan(0);
        const last = points[points.length - 1];
        expect
          .soft(last.total_value, `portfolio value in ${currency}`)
          .toBe((await portfolio.json()).total_value);
      }
    } finally {
      await request.patch(`${API_BASE}/investments/${id}/archive`, { headers });
    }
  });

  test('every finance aggregate adds up to the rows it summarises', async ({ request }) => {
    /*
     * Rows, period totals, monthly bars and the category donut all convert each day at its own rate,
     * over the same daily buckets — so the three aggregates agree to the cent, and they equal the sum of
     * the converted rows the /expenses and /income lists show. Before, the totals converted each MONTH
     * at its last day and the donut the whole period at its end, so one account read three different
     * all-time expense figures. Rows sharing a day, category and currency are converted once as a
     * bucket, so the rows' own sum may sit up to half a cent per row away; the aggregates may not.
     */
    const token = await apiToken();
    const headers = { Authorization: `Bearer ${token}` };
    const get = async (path: string) => {
      const response = await request.get(`${API_BASE}${path}`, { headers });
      expect(response.ok(), `GET ${path}: ${response.status()}`).toBe(true);
      return response.json();
    };
    // Every converted row of a list, across all its pages.
    const listedRows = async (path: string, currency: string) => {
      const amounts: number[] = [];
      for (let page = 1; ; page += 1) {
        const body = await get(`${path}?currency=${currency}&scope=all&page_size=100&page=${page}`);
        for (const item of body.items) {
          if (item.converted_amount !== null) amounts.push(Number(item.converted_amount));
        }
        if (page * 100 >= body.total) return amounts;
      }
    };

    let anyRows = false;
    for (const currency of await displayCurrencies(request, token)) {
      const overview = await get(`/finance-metrics/overview?currency=${currency}`);
      const monthly = await get(`/finance-metrics/monthly?currency=${currency}`);
      const expenseDonut = await get(`/finance-metrics/expense-breakdown?currency=${currency}`);
      const incomeDonut = await get(`/finance-metrics/income-breakdown?currency=${currency}`);
      const dashboard = await get(`/dashboard/overview?currency=${currency}`);
      // Cents, so the sums compare exactly rather than through float drift.
      const cents = (value: string | number) => Math.round(Number(value) * 100);
      const monthlySum = (key: 'income' | 'expenses') =>
        monthly.points.reduce((sum: number, p: Record<string, string>) => sum + cents(p[key]), 0);

      expect
        .soft(cents(expenseDonut.total_expenses), `expense donut in ${currency}`)
        .toBe(cents(overview.total_expenses));
      expect
        .soft(cents(incomeDonut.total_income), `income donut in ${currency}`)
        .toBe(cents(overview.total_income));
      expect
        .soft(monthlySum('expenses'), `monthly expenses in ${currency}`)
        .toBe(cents(overview.total_expenses));
      expect
        .soft(monthlySum('income'), `monthly income in ${currency}`)
        .toBe(cents(overview.total_income));
      expect
        .soft(dashboard.total_expenses, `dashboard expenses in ${currency}`)
        .toBe(overview.total_expenses);

      for (const [path, total] of [
        ['/expenses', overview.total_expenses],
        ['/income', overview.total_income],
      ] as const) {
        const rows = await listedRows(path, currency);
        anyRows ||= rows.length > 0;
        const rowSum = rows.reduce((sum, amount) => sum + Math.round(amount * 100), 0);
        expect
          .soft(Math.abs(rowSum - cents(total)), `${path} rows against the total in ${currency}`)
          .toBeLessThanOrEqual(Math.ceil(rows.length / 2));
      }
    }
    test.skip(!anyRows, 'the harness account has no expense or income rows to add up');
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

    /*
     * Picked by POSITION rather than by label, because the switcher renders
     * `[primary, secondary?, original]` — so the first radio is whatever this account's primary is and
     * the last is always "Original". Naming a currency would tie the spec to one account's settings,
     * and this way the structure being relied on is the thing asserted.
     */
    const radios = switcher.getByRole('radio');
    const hint = page.getByTestId('hint-currency-hint-dismissed');

    // "Original" is the one selection where nothing converts, so the sentence about which rate is used
    // has nothing to explain and the page withholds it.
    await radios.last().click();
    await expect(hint).toBeHidden();

    // Any real currency converts, so the hint returns. Asserting the SENTENCE and not merely the
    // element: this unit rewrote it because the old one described a basis the dashboard stopped using,
    // and an element-only assertion would pass on the copy it was written to replace.
    await radios.first().click();
    await expect(hint).toBeVisible();
    await expect(hint).toContainText('uses the rate of that date');
  });
});
