import AxeBuilder from '@axe-core/playwright';
import { test as base, expect, type Page, type TestInfo } from '@playwright/test';

import { A11Y_ALLOW_LIST } from './a11y-allowlist';
import { WEB_BASE } from './api';
import { settle } from './overflow';

// axe-core's own types, reached through the builder rather than a second dependency on axe-core.
type AxeResults = Awaited<ReturnType<AxeBuilder['analyze']>>;
type Result = AxeResults['violations'][number];

/*
 * The accessibility scan every spec uses: one preset, one assertion, one allow-list.
 *
 * `test` here is Playwright's `test` extended with `makeAxeBuilder`, which returns an `AxeBuilder`
 * already set to the rule tags below. A spec narrows it (`.include()` an open dialog) and hands the
 * results to `expectNoA11yViolations`, which attaches the whole result to the report and then fails on
 * any violation not in `A11Y_ALLOW_LIST`. The `@a11y` tag on those specs selects them all:
 * `pnpm test:e2e --grep @a11y`.
 *
 * The tags are WCAG 2.0, 2.1 and 2.2 at levels A and AA plus axe's `best-practice` set. The last is on
 * purpose: `page-has-heading-one`, `region` (content outside every landmark) and `landmark-unique` are
 * best-practice rules, and they are exactly the class the first audit found — a WCAG-only preset would
 * pass all of it.
 */
export const AXE_TAGS = [
  'wcag2a',
  'wcag2aa',
  'wcag21a',
  'wcag21aa',
  'wcag22aa',
  'best-practice',
] as const;

/*
 * Rules a whole-page scan must have RUN, whether they passed, failed, could not decide, or found
 * nothing to check. Each stands for one part of the preset: `target-size` exists only under
 * `wcag22aa`, `page-has-heading-one` only under `best-practice`. If a tag stops reaching axe — a typo, an
 * axe upgrade renaming it — the scan still returns zero violations, just over fewer rules, and this is
 * what notices.
 */
const RULES_THE_PRESET_RUNS = ['target-size', 'page-has-heading-one', 'color-contrast'] as const;

/*
 * `nextjs-portal` is the dev server's own overlay (the route indicator, the error toasts). It is not
 * part of the app and a production build never renders it, so it is left out of every scan — the one
 * standing exclusion, and not an exception: nothing the app ships is inside it.
 */
export const test = base.extend<{ makeAxeBuilder: () => AxeBuilder }>({
  // `provide` is Playwright's `use` callback, renamed so the React hooks lint rule does not take it
  // for React's `use`.
  makeAxeBuilder: async ({ page }, provide) => {
    await provide(() => new AxeBuilder({ page }).withTags([...AXE_TAGS]).exclude('nextjs-portal'));
  },
});

export { expect };

// Waits for what a scan must not see half-done: fonts, running animations (a dialog mid-fade has
// half-contrast text), and a pending navigation.
export async function settleForScan(page: Page): Promise<void> {
  await page.waitForLoadState('load');
  await settle(page);
  /*
   * Two things `settle` cannot see. motion/react runs some animations on its own frame loop rather
   * than as Web Animations, and some content mounts AFTER load — the cookie banner appears from an
   * effect, then slides and fades in. Scanned mid-fade, its text sits at a fraction of its contrast
   * and axe reports that, on some runs and not others. So the page must be QUIET for a whole window:
   * no element at an inline opacity strictly between 0 and 1 (a fade in flight; nothing at rest looks
   * like that) and no finite animation running, twice in a row, QUIET_MS apart.
   */
  const moving = () =>
    page.evaluate(
      () =>
        [...document.querySelectorAll<HTMLElement>('[style*="opacity"]')].filter((element) => {
          const opacity = Number(element.style.opacity);
          return opacity > 0 && opacity < 1;
        }).length +
        document
          .getAnimations()
          .filter(
            (animation) =>
              animation.playState === 'running' &&
              animation.effect?.getComputedTiming().endTime !== Infinity,
          ).length,
    );
  const deadline = Date.now() + SETTLE_TIMEOUT_MS;
  let quietSince: number | null = null;
  while (Date.now() < deadline) {
    if ((await moving()) > 0) quietSince = null;
    else if (quietSince === null) quietSince = Date.now();
    else if (Date.now() - quietSince >= QUIET_MS) return;
    await page.waitForTimeout(100);
  }
  throw new Error(`the page never stopped animating within ${SETTLE_TIMEOUT_MS}ms`);
}

// How long the page must be still before a scan, and how long to wait for that.
const QUIET_MS = 400;
const SETTLE_TIMEOUT_MS = 8_000;

/*
 * Loads `path` in `locale` and waits until it can be scanned. Fails when the app sent the visit
 * somewhere else — a redirect would scan a different page under this one's name — or rendered the
 * other language.
 */
export async function openForScan(page: Page, path: string, locale: 'en' | 'es'): Promise<void> {
  await page
    .context()
    .addCookies([
      { name: 'NEXT_LOCALE', value: locale, domain: new URL(WEB_BASE).hostname, path: '/' },
    ]);
  await page.goto(path);
  await expect(page.locator('html')).toHaveAttribute('lang', locale);
  expect(new URL(page.url()).pathname, `${path} redirected`).toBe(new URL(path, WEB_BASE).pathname);
  // Every test context is a first visit, so the cookie banner is part of every page scanned. It mounts
  // from an effect after hydration; waiting for it makes each scan include it, and not half-faded.
  await page.getByTestId('cookie-consent').waitFor();
  await settleForScan(page);
}

// A file-safe attachment name for a path and locale, e.g. `shared_pots_12-es`.
export function scanName(path: string, locale: string): string {
  const slug = path.replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '') || 'root';
  return `${slug}-${locale}`;
}

// The violations the allow-list does not cover. A node is covered when an entry names its rule and the
// entry's selector matches the element axe reported.
async function unexcused(page: Page, violations: Result[]): Promise<Result[]> {
  if (A11Y_ALLOW_LIST.length === 0) return violations;
  const kept: Result[] = [];
  for (const violation of violations) {
    const entries = A11Y_ALLOW_LIST.filter((entry) => entry.rule === violation.id);
    const nodes = [];
    for (const node of violation.nodes) {
      const target = node.target[node.target.length - 1];
      const excused =
        typeof target === 'string' &&
        (await page.evaluate(
          ({ target, selectors }) => {
            const element = document.querySelector(target);
            return !!element && selectors.some((selector) => element.matches(selector));
          },
          { target, selectors: entries.map((entry) => entry.selector) },
        ));
      if (!excused) nodes.push(node);
    }
    if (nodes.length > 0) kept.push({ ...violation, nodes });
  }
  return kept;
}

// One line per violation, naming the rule, its impact and every element it fired on — what the test
// failure prints. The full result (help URLs, the failing HTML, the reasons) is in the attachment.
function summarize(violations: Result[]): string[] {
  return violations.map(
    (violation) =>
      `${violation.id} (${violation.impact ?? 'n/a'}): ${violation.help} — ` +
      violation.nodes.map((node) => node.target.join(' ')).join(', '),
  );
}

/*
 * Attaches the full axe result to the test report, then fails on every violation the allow-list does
 * not excuse. `name` labels the attachment (e.g. the route and locale). `wholePage` asks for the preset
 * check above; a scan narrowed by `include()` leaves most page-level rules inapplicable, so it passes
 * false.
 */
export async function expectNoA11yViolations(
  page: Page,
  results: AxeResults,
  testInfo: TestInfo,
  name: string,
  { wholePage }: { wholePage: boolean },
): Promise<void> {
  await testInfo.attach(`axe-${name}.json`, {
    body: JSON.stringify(results, null, 2),
    contentType: 'application/json',
  });

  if (wholePage) {
    const ran = new Set(
      [
        ...results.passes,
        ...results.violations,
        ...results.incomplete,
        ...results.inapplicable,
      ].map((rule) => rule.id),
    );
    expect(
      RULES_THE_PRESET_RUNS.filter((rule) => !ran.has(rule)),
      'the axe preset no longer runs these rules — a tag stopped reaching axe',
    ).toEqual([]);
  }

  expect(summarize(await unexcused(page, results.violations)), `axe violations on ${name}`).toEqual(
    [],
  );
}
