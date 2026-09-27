import { expect, test, type Page } from '@playwright/test';

import {
  LEGEND_ROUTES,
  MONEY_SWEEP_ROUTES,
  SWEEP_WIDTHS,
  type MoneySweepRoute,
} from './helpers/money-pages';
import { seedMoney, type MoneySeed } from './helpers/money-seed';
import { findSettledClipping } from './helpers/overflow';

/*
 * No money figure is ever cut off, on any page that shows one, at any width from 320 to 1920, in
 * either language.
 *
 * The defect this pins printed a DIFFERENT number rather than a broken one: at 1024px the dashboard's
 * five cards were ~130px wide, the figures ran past them, and the page's `overflow-x-hidden` hid the
 * tail — "5,296,553." for 5,296,553.12 — with no ellipsis, so nothing said a digit was missing. Every figure is marked `data-money` by `MoneyFigure`, and the harness in
 * `helpers/overflow.ts` checks each one against its own box, the box it sits in, and every clipping
 * ancestor.
 *
 * Three things keep the sweep from passing vacuously, which is the failure it would otherwise have:
 *   * the seed carries figures long enough to overflow (see `helpers/money-seed.ts`) — the harness
 *     account's own may all be short;
 *   * every page must show at least one marked figure, and every donut page at least one legend
 *     name, so a page whose marker or legend went missing fails here instead of passing with nothing
 *     checked;
 *   * the page list is derived — `tests/unit/money-sweep-coverage.test.ts` fails when a page that
 *     renders money is neither swept nor skipped with a reason.
 *
 * And one thing beyond "not clipped": a typical long figure (up to thirteen characters, like
 * -3,923,637.12) renders at its full design size. `MetricCard`'s fit would otherwise make the headline
 * cards pass at any column count by shrinking the digits — legible, but not the layout's job done.
 * Only a figure too long for any card (the seed's 123,456,789,012.34) may shrink.
 */

// The longest a figure may be and still be owed its full design size.
const TYPICAL_FIGURE_CHARS = 13;
// Tall enough that the headline cards and the donut are on screen together at every width.
const SWEEP_HEIGHT = 1000;

/*
 * The time budget, which has to fit inside CI's 30-minute e2e job next to every other spec.
 *
 * One test per locale sweeps all thirteen pages, so a budget covers a whole sweep: locally 600s, because
 * a cold dev server compiles each route on first visit (45s for one was measured); in CI 240s, since the
 * production build compiles nothing and a green sweep takes about a minute there. Retries are OFF for
 * this file: the harness already re-measures a layout that is still settling, so a retry could only
 * repeat a real finding at the cost of another whole sweep. Worst case in CI is therefore 2 × 240s =
 * 8 minutes, however broken the pages are.
 */
// eslint-disable-next-line turbo/no-undeclared-env-vars
const ciEnv = process.env.CI;
const isCI = !!ciEnv && ciEnv !== 'false' && ciEnv !== '0';
const SWEEP_BUDGET_MS = isCI ? 240_000 : 600_000;

test.describe.configure({ retries: 0 });

let seed: MoneySeed;

test.beforeAll(async () => {
  seed = await seedMoney();
});

test.afterAll(async () => {
  await seed?.cleanup();
});

function url(route: MoneySweepRoute): string {
  if (route === '/accounts/[id]') return `/accounts/${seed.accountId}`;
  if (route === '/payments-calendar')
    return `/payments-calendar?year=${seed.scheduledYear}&month=${seed.scheduledMonth}`;
  return route;
}

// Fitted figures of typical length that are rendered smaller than their parent's size — i.e. figures
// the layout failed to make room for.
async function shrunkTypicalFigures(page: Page): Promise<string[]> {
  return page.evaluate((maxChars) => {
    return [...document.querySelectorAll<HTMLElement>('[data-money]')]
      .filter((el) => el.style.fontSize !== '' && (el.textContent ?? '').length <= maxChars)
      .filter((el) => {
        const own = parseFloat(getComputedStyle(el).fontSize);
        const parent = el.parentElement
          ? parseFloat(getComputedStyle(el.parentElement).fontSize)
          : own;
        return own < parent - 0.5;
      })
      .map((el) => `${el.textContent} at ${getComputedStyle(el).fontSize}`);
  }, TYPICAL_FIGURE_CHARS);
}

for (const locale of ['en', 'es'] as const) {
  test(`no money figure is clipped, at any width (${locale})`, async ({ page }) => {
    test.setTimeout(SWEEP_BUDGET_MS);
    await page
      .context()
      .addCookies([{ name: 'NEXT_LOCALE', value: locale, domain: 'localhost', path: '/' }]);

    const failures: string[] = [];
    for (const route of MONEY_SWEEP_ROUTES) {
      // Loaded once, then resized through every width: the same page reflowing is what a reader
      // resizing a window or rotating a tablet sees, and one load per page keeps the cost down.
      await page.setViewportSize({ width: Math.max(...SWEEP_WIDTHS), height: SWEEP_HEIGHT });
      await page.goto(url(route));
      await expect(page.locator('html')).toHaveAttribute('lang', locale);

      for (const width of SWEEP_WIDTHS) {
        await page.setViewportSize({ width, height: SWEEP_HEIGHT });
        const where = `${route} @${width}px`;

        const money = await findSettledClipping(page, '[data-money]');
        if (money.matched === 0) failures.push(`${where}: no [data-money] figure on the page`);
        money.clipped.forEach((c) => failures.push(`${where}: "${c.text}" — ${c.reason}`));

        (await shrunkTypicalFigures(page)).forEach((figure) =>
          failures.push(`${where}: typical figure shrunk to fit — ${figure}`),
        );

        if (LEGEND_ROUTES.includes(route)) {
          const legend = await findSettledClipping(page, '[data-testid="chart-legend-label"]');
          if (legend.matched === 0) failures.push(`${where}: no legend name on the page`);
          legend.clipped.forEach((c) =>
            failures.push(`${where}: legend "${c.text}" — ${c.reason}`),
          );
        }
      }
    }

    expect(failures).toEqual([]);
  });
}
