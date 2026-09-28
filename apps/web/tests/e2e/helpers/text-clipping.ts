import { expect, type Page } from '@playwright/test';

import { findSettledClipping, type Clipping, type ClippingReport } from './overflow';

/*
 * The text sweep's half of the overflow harness: which elements carry text, and which cut-off text is
 * a deliberate truncation rather than a defect.
 *
 * WHAT IS MEASURED. Every element holding a non-blank text node of its own — the element the words are
 * laid out in, however deep it sits — except text no sighted reader is meant to see (a visually-hidden
 * `sr-only` span, Radix's hidden tooltip copy) and elements that hold no laid-out prose (scripts,
 * styles, `<option>`s, `<textarea>`s). Each one is tagged `data-text-probe` so the generic harness can
 * measure it through a selector.
 *
 * WHAT IS ALLOWED. A cut-off text is a deliberate truncation, and not a finding, only when ALL of:
 *   1. the only failure is its own box (`ownBoxOnly`): nothing around it cuts it off or is printed
 *      over — a truncated name whose box is itself clipped by its card is still a clipped name;
 *   2. the element draws an ellipsis itself (`ellipsis`): a block that clips on X, does not wrap and
 *      sets `text-overflow: ellipsis`, i.e. `truncate` on a block. `truncate` on a FLEX container
 *      draws no ellipsis — the text is simply cut — so it does not count;
 *   3. the page offers the full text (`cue`): a `title` equal to the whole text, or a tooltip trigger
 *      whose tooltip, once opened, reads the whole text (`tooltipShowsFullText` opens it — a trigger
 *      is only a claim). An `aria-label` does not count: the DOM already gives assistive tech the
 *      whole text, and what the truncation hides it hides from SIGHTED readers, whom only a visible
 *      cue reaches;
 *   4. the box still shows a real part of the text: at least `MIN_VISIBLE_EM` ems of its own font
 *      size. A name squeezed to two letters and an ellipsis is hidden, not truncated, whatever its
 *      tooltip says — which is what a shrink-0 badge beside it did on /payments-calendar in Spanish.
 * `tests/e2e/truncation-rule.spec.ts` pins each clause against a page built to break it.
 */

// Six ems is about eight characters of body text: enough to tell two names apart. The narrowest
// deliberate truncation in the app (a sidebar item's label) shows about eight and a half.
export const MIN_VISIBLE_EM = 6;

export const TEXT_PROBE_ATTRIBUTE = 'data-text-probe';
// Set by the harness on each clipped element, so a tooltip cue can be hovered and read.
export const CLIPPED_MARK_ATTRIBUTE = 'data-text-clipped';

// Tags every element that lays out its own visible text, and removes tags left by an earlier call.
export async function markTextElements(page: Page): Promise<void> {
  await page.evaluate((attribute) => {
    document.querySelectorAll(`[${attribute}]`).forEach((el) => el.removeAttribute(attribute));
    const skipped = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'OPTION', 'TEXTAREA']);
    const clips = (value: string) => value === 'hidden' || value === 'clip';
    // `sr-only` and Radix's VisuallyHidden: a clipping box of at most one pixel.
    const visuallyHidden = (el: Element) => {
      for (let node: Element | null = el; node; node = node.parentElement) {
        const rect = node.getBoundingClientRect();
        const style = getComputedStyle(node);
        const hides =
          clips(style.overflowX) ||
          style.clipPath !== 'none' ||
          (style.clip && style.clip !== 'auto');
        if (rect.width <= 1 && rect.height <= 1 && hides) return true;
      }
      return false;
    };
    document.body.querySelectorAll('*').forEach((el) => {
      if (skipped.has(el.tagName)) return;
      const ownText = [...el.childNodes].some(
        (node) => node.nodeType === Node.TEXT_NODE && /\S/.test(node.textContent ?? ''),
      );
      if (ownText && !visuallyHidden(el)) el.setAttribute(attribute, '');
    });
  }, TEXT_PROBE_ATTRIBUTE);
}

// Clauses 1-4 of the rule above, as far as the DOM alone can answer them. A `tooltip` cue still has to
// pass `tooltipShowsFullText`.
export function isAllowedTruncation(clipping: Clipping): boolean {
  return (
    clipping.ownBoxOnly &&
    clipping.ellipsis &&
    clipping.cue !== null &&
    clipping.visibleEm >= MIN_VISIBLE_EM
  );
}

// Why a clipping is a finding, in the rule's terms.
export function describeFinding(clipping: Clipping): string {
  if (!clipping.ownBoxOnly) return clipping.reason;
  if (!clipping.ellipsis) return `${clipping.reason}, cut with no ellipsis`;
  if (clipping.cue === null) return `${clipping.reason}, truncated with no full-text cue`;
  return `${clipping.reason}, squeezed to ${clipping.visibleEm.toFixed(1)}em (under ${MIN_VISIBLE_EM}em shows almost nothing)`;
}

// Every text element on the page, measured once the layout has settled. The retry only waits on
// findings, so a page whose one clipping is an allowed truncation does not sit out the budget.
export async function findClippedText(page: Page): Promise<ClippingReport> {
  await markTextElements(page);
  return findSettledClipping(
    page,
    `[${TEXT_PROBE_ATTRIBUTE}]`,
    3_000,
    (clipping) => !isAllowedTruncation(clipping),
    { markAttribute: CLIPPED_MARK_ATTRIBUTE },
  );
}

/*
 * How many visible text elements the page's OWN content holds — inside `<main>`. The report's `matched`
 * counts the sidebar, the header and the cookie notice too, which are on every page, so it can never
 * be zero; a page whose content failed to render would pass a check on it. Call after
 * `findClippedText`, which tags the elements.
 */
export async function countTextInMain(page: Page): Promise<number> {
  return page.evaluate(
    (attribute) =>
      [...document.querySelectorAll(`main [${attribute}]`)].filter(
        (el) => el.getClientRects().length > 0 && el.checkVisibility({ visibilityProperty: true }),
      ).length,
    TEXT_PROBE_ATTRIBUTE,
  );
}

// Opens the tooltip on a clipped element (found by the mark the harness left) and checks it reads the
// element's whole text; then closes it, so it is not measured as page text afterwards.
export async function tooltipShowsFullText(page: Page, clipping: Clipping): Promise<boolean> {
  const target = page.locator(`[${CLIPPED_MARK_ATTRIBUTE}="${clipping.index}"]`);
  const fullText = clipping.text.replace(/\s+/g, ' ').trim();
  const tooltip = page.getByRole('tooltip');
  /*
   * The cookie notice is fixed over the bottom of the viewport, and a row near the end of a page
   * cannot scroll out from under it. It is hidden for the hover only — its own copy is page text the
   * sweep measures like any other.
   */
  const notice = page.getByTestId('cookie-consent');
  await notice.evaluateAll((els) =>
    els.forEach((el) => ((el as HTMLElement).style.visibility = 'hidden')),
  );
  await target.hover();
  let shown = true;
  try {
    await expect(tooltip).toHaveText(fullText, { timeout: 2_000 });
  } catch {
    shown = false;
  }
  /*
   * Two moves, not one: Radix keeps a tooltip open while the pointer crosses the gap to its content,
   * and it decides the pointer has left on the pointermove AFTER the one that left the trigger — a
   * single jump away leaves it open for good.
   */
  await page.mouse.move(0, 0);
  await page.mouse.move(1, 1);
  await expect(tooltip).toHaveCount(0);
  await notice.evaluateAll((els) =>
    els.forEach((el) => ((el as HTMLElement).style.visibility = '')),
  );
  return shown;
}
