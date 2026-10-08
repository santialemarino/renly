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
 * The tag set the project DECIDED on (P2-D1), kept apart from `AXE_TAGS` on purpose: the check below
 * compares what the scan actually ran against THIS list, so editing the builder's tags — dropping one,
 * mistyping one — goes red instead of quietly moving the check along with it. The two lists must be
 * changed together, deliberately.
 */
const DECIDED_TAGS = [
  'wcag2a',
  'wcag2aa',
  'wcag21a',
  'wcag21aa',
  'wcag22aa',
  'best-practice',
] as const;

/*
 * Decided tags that no rule axe runs carries YET, each with the rule that holds it back. They stay in
 * `AXE_TAGS`, so the day axe ships a runnable rule under one it runs with no edit here; they are only
 * spared the "reached" half of the check below, since no scan can reach them today.
 *
 * Measured against axe-core 4.13.0's rule metadata: the ONLY rule tagged `wcag21a` is
 * `label-content-name-mismatch` (WCAG 2.5.3), and it is also tagged `experimental`. A run selected by
 * tags (`withTags`, i.e. `runOnly: { type: 'tag' }`) excludes every `experimental` rule unless
 * `experimental` is itself one of the tags, so that rule never runs and `wcag21a` appears in no result.
 *
 * The exemption cannot outlive its reason: a whole-page scan in which an exempt tag DOES appear fails
 * by name (see `outlivedExemptions`), so an axe upgrade that promotes the rule out of `experimental`
 * removes this entry the same day.
 */
const NOT_YET_RUNNABLE: Partial<Record<(typeof DECIDED_TAGS)[number], string>> = {
  wcag21a:
    'label-content-name-mismatch is its only rule in axe-core 4.13.0, and it is experimental',
};

// The tags asked for (`toolOptions.runOnly`) and the tags carried by the rules that ran — passed,
// failed, undecided or inapplicable, since every rule that ran lands in one of the four.
function tagsOf(results: AxeResults): { asked: Set<string>; carried: Set<string> } {
  return {
    asked: new Set<string>(
      (results.toolOptions.runOnly as { values?: string[] } | undefined)?.values ?? [],
    ),
    carried: new Set(
      [
        ...results.passes,
        ...results.violations,
        ...results.incomplete,
        ...results.inapplicable,
      ].flatMap((rule) => rule.tags),
    ),
  };
}

/*
 * The decided tags a whole-page scan did NOT reach, derived from the result itself. A tag counts as
 * reached when axe was asked for it and at least one rule carrying it ran. A tag that stops reaching
 * axe (dropped from the builder, renamed by an axe upgrade) still leaves a result with zero violations,
 * just over fewer rules; this is what notices. Every decided tag must be ASKED for, exempt or not; an
 * exempt one is spared only the "ran" half.
 */
function unreachedTags(results: AxeResults): string[] {
  const { asked, carried } = tagsOf(results);
  return DECIDED_TAGS.filter(
    (tag) => !asked.has(tag) || (!carried.has(tag) && !(tag in NOT_YET_RUNNABLE)),
  );
}

// The exempt tags a scan reached after all: each one's exemption has outlived its reason.
function outlivedExemptions(results: AxeResults): string[] {
  const { carried } = tagsOf(results);
  return Object.keys(NOT_YET_RUNNABLE).filter((tag) => carried.has(tag));
}

/*
 * `nextjs-portal` is the dev server's own overlay (the route indicator, the error toasts). It is not
 * part of the app and a production build never renders it, so it is left out of every scan — the one
 * standing exclusion, and not an exception: nothing the app ships is inside it.
 */
export function presetAxeBuilder(page: Page): AxeBuilder {
  return new AxeBuilder({ page }).withTags([...AXE_TAGS]).exclude('nextjs-portal');
}

// The fixture most specs use; `presetAxeBuilder` directly is for a page from a context of its own.
export const test = base.extend<{ makeAxeBuilder: () => AxeBuilder }>({
  // `provide` is Playwright's `use` callback, renamed so the React hooks lint rule does not take it
  // for React's `use`.
  makeAxeBuilder: async ({ page }, provide) => {
    await provide(() => presetAxeBuilder(page));
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

// What the app renders instead of a page: the not-found screen and the error boundary (`ErrorState`,
// which every error boundary and `global-error` render).
const NOT_FOUND = '[data-testid="not-found"]';
const ERROR_BOUNDARY = '[data-testid="error-boundary"]';

/*
 * Loads `path` in `locale` and waits until it can be scanned. Fails when the scan would be about a
 * different page than the one it names:
 *   * the app redirected the visit elsewhere;
 *   * it rendered the other language;
 *   * it rendered the not-found screen or an error boundary INSTEAD of the page — a route whose seed no
 *     longer satisfies it (`notFound()` on a pot that cannot be bought out) passes a scan of the 404
 *     off as a scan of the page. Only the two not-found targets pass `notFound: true`, and for them the
 *     not-found screen is REQUIRED, so they cannot silently become a scan of something else either.
 */
export async function openForScan(
  page: Page,
  path: string,
  locale: 'en' | 'es',
  { notFound = false }: { notFound?: boolean } = {},
): Promise<void> {
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
  expect(
    await page.locator(ERROR_BOUNDARY).count(),
    `${path} rendered the error boundary, not the page`,
  ).toBe(0);
  expect(
    await page.locator(NOT_FOUND).count(),
    notFound
      ? `${path} was expected to render the not-found page`
      : `${path} rendered the not-found page, not the page`,
  ).toBe(notFound ? 1 : 0);
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
    expect(unreachedTags(results), 'these decided axe tags did not reach the scan').toEqual([]);
    expect(
      outlivedExemptions(results),
      'these axe tags now reach the scan: remove them from NOT_YET_RUNNABLE in helpers/axe.ts',
    ).toEqual([]);
  }

  expect(summarize(await unexcused(page, results.violations)), `axe violations on ${name}`).toEqual(
    [],
  );
}
