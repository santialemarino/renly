import { expect, test } from '@playwright/test';

import { seedGroup, type GroupSeed } from './helpers/group-seed';
import { seedMoney, type MoneySeed } from './helpers/money-seed';
import {
  countTextInMain,
  describeFinding,
  findClippedText,
  isAllowedTruncation,
  tooltipShowsFullText,
  waitForPageContent,
} from './helpers/text-clipping';
import { TEXT_SWEEP_WIDTHS, textSweepRoutes } from './helpers/text-pages';

/*
 * No text on the app surface is cut off, in Spanish or in English, at any width from 360 to 1280 —
 * except a deliberate truncation that draws an ellipsis AND offers the whole text (the exact rule is in
 * `helpers/text-clipping.ts`, and `truncation-rule.spec.ts` pins it).
 *
 * The class this guards: Spanish runs 20-30% longer than English, so copy sized in English runs out of
 * its box in Spanish. Measured before the fix: at 390px "Por colección" was cut mid-word by 19.1px (a
 * toggle group that shrank below its labels), and on /payments-calendar the "Vencimiento de tarjeta"
 * badge left a card's name 37% of its width, truncated with no way to read the rest. English runs as
 * the control, and is held to the same rule.
 *
 * Kept from passing vacuously: every page is derived from the route tree (`helpers/text-pages.ts`,
 * held to the tree by a unit test), every page must show text of its own inside `<main>` at every width
 * (the shell's sidebar and header would make a whole-page count pass on an empty page), and the
 * money sweep's seed puts long names on screen — the marker-named card, account and schedules, and
 * the longest Spanish category names — while `helpers/group-seed.ts` gives the shared pages a group, a
 * long Spanish seat name and an empty pot.
 */

// Tall enough that the dashboards' cards and donut are on screen together at every width.
const SWEEP_HEIGHT = 1000;

/*
 * The time budget, for one locale's whole sweep: locally 900s, because a cold dev server compiles each
 * of ~25 routes on first visit; in CI 300s, where the production build compiles nothing. Retries are off
 * for the same reason as the money sweep's: the harness already re-measures a layout still settling,
 * so a retry could only repeat a real finding at the cost of another whole sweep.
 */
// eslint-disable-next-line turbo/no-undeclared-env-vars
const ciEnv = process.env.CI;
const isCI = !!ciEnv && ciEnv !== 'false' && ciEnv !== '0';
const SWEEP_BUDGET_MS = isCI ? 300_000 : 900_000;
// A cold dev server's first compile of a route can outlast the default 30s navigation timeout.
const NAVIGATION_TIMEOUT_MS = isCI ? 30_000 : 120_000;

test.describe.configure({ retries: 0 });

let seed: MoneySeed;
let group: GroupSeed;

test.beforeAll(async () => {
  seed = await seedMoney();
  group = await seedGroup();
});

test.afterAll(async () => {
  await group?.cleanup();
  await seed?.cleanup();
});

// The URL for a route pattern. A dynamic route with no entry here throws, naming it — the unit test
// makes it a skip instead, so this only fires if the two drift.
function url(route: string): string {
  if (route === '/accounts/[id]') return `/accounts/${seed.accountId}`;
  if (route === '/shared/[groupId]') return `/shared/${group.groupId}`;
  if (route === '/shared/[groupId]/share') return `/shared/${group.groupId}/share`;
  if (route === '/shared/pots/[id]') return `/shared/pots/${group.potId}`;
  if (route === '/payments-calendar')
    return `/payments-calendar?year=${seed.scheduledYear}&month=${seed.scheduledMonth}`;
  if (route.includes('[')) throw new Error(`no URL for dynamic route ${route}`);
  return route;
}

for (const locale of ['es', 'en'] as const) {
  test(`no text is clipped without a full-text cue, at any width (${locale})`, async ({ page }) => {
    test.setTimeout(SWEEP_BUDGET_MS);
    await page
      .context()
      .addCookies([{ name: 'NEXT_LOCALE', value: locale, domain: 'localhost', path: '/' }]);

    const failures: string[] = [];
    for (const route of textSweepRoutes()) {
      await page.setViewportSize({ width: Math.max(...TEXT_SWEEP_WIDTHS), height: SWEEP_HEIGHT });
      await page.goto(url(route), { timeout: NAVIGATION_TIMEOUT_MS });
      if (!(await waitForPageContent(page))) {
        failures.push(`${route}: its own content never rendered inside <main>`);
        continue;
      }
      await expect(page.locator('html')).toHaveAttribute('lang', locale);

      for (const width of TEXT_SWEEP_WIDTHS) {
        await page.setViewportSize({ width, height: SWEEP_HEIGHT });
        const where = `${route} @${width}px`;

        const report = await findClippedText(page);
        /*
         * The app's not-found page and its error boundary have text of their own, so a page that
         * failed would pass every check here. The status cannot say so — behind a loading screen the
         * response is already a streaming 200 when the page calls notFound(), and the not-found page
         * replaces the skeleton after load — so it is read off the settled screen instead.
         */
        const failed = page.getByTestId('not-found').or(page.getByTestId('error-boundary'));
        if ((await failed.count()) > 0) {
          failures.push(
            `${where}: rendered the not-found page or the error boundary, not the page`,
          );
          break;
        }
        if ((await countTextInMain(page)) === 0) {
          failures.push(`${where}: no text inside <main> — the page's own content did not render`);
        }
        for (const clipping of report.clipped) {
          if (!isAllowedTruncation(clipping)) {
            failures.push(`${where}: "${clipping.text}" — ${describeFinding(clipping)}`);
          } else if (clipping.cue === 'tooltip' && !(await tooltipShowsFullText(page, clipping))) {
            failures.push(
              `${where}: "${clipping.text}" — truncated, and its tooltip does not show the full text`,
            );
          }
        }
      }
    }

    expect(failures).toEqual([]);
  });
}
