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
 *      whose tooltip, once opened, reads the whole text (`tooltipShowsFullText` opens it by hover and
 *      `tooltipOpensFromKeyboard` by focus — a trigger is only a claim, and a hover-only tooltip
 *      leaves keyboard users without the text). An `aria-label` does not count: the DOM already
 *      gives assistive tech the whole text, and what the truncation hides it hides from SIGHTED
 *      readers, whom only a visible cue reaches;
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
 * be zero; a page whose content failed to render would pass a check on it. Tags the page first.
 */
export async function countTextInMain(page: Page): Promise<number> {
  await markTextElements(page);
  return page.evaluate(
    (attribute) =>
      [...document.querySelectorAll(`main [${attribute}]`)].filter(
        (el) => el.getClientRects().length > 0 && el.checkVisibility({ visibilityProperty: true }),
      ).length,
    TEXT_PROBE_ATTRIBUTE,
  );
}

/*
 * Waits until the page's own content is on screen: its loading skeleton gone and text of its own
 * inside `<main>`. `goto` resolves on the document's load, and behind a loading screen the content
 * streams in AFTER that — measured then, a page is its skeleton, or an empty main between the two,
 * and every check passes on it. Returns false when the content never came, so the caller reports it.
 */
export async function waitForPageContent(page: Page, timeout = 15_000): Promise<boolean> {
  try {
    await expect(page.getByTestId('page-skeleton')).toHaveCount(0, { timeout });
    await expect.poll(() => countTextInMain(page), { timeout }).toBeGreaterThan(0);
    return true;
  } catch {
    return false;
  }
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

const KEYBOARD_STOP_ATTRIBUTE = 'data-text-keyboard-stop';

/*
 * The same tooltip, reached from the KEYBOARD (WCAG 2.1.1 and 1.4.13): the clipped element — or, when
 * it sits inside a link or a button, that element — is in the tab order, focusing it opens the tooltip
 * with the whole text, and Escape closes it. Returns why it failed, or null.
 *
 * Focus is moved by script right after a key press, which the browser treats as keyboard focus
 * (`:focus-visible`) — the focus a Tab gives, without walking the page's whole tab order. That the
 * element really is IN the tab order is read from `tabIndex`, the browser's own answer.
 */
export async function tooltipOpensFromKeyboard(
  page: Page,
  clipping: Clipping,
): Promise<string | null> {
  const target = page.locator(`[${CLIPPED_MARK_ATTRIBUTE}="${clipping.index}"]`);
  const fullText = clipping.text.replace(/\s+/g, ' ').trim();
  const tooltip = page.getByRole('tooltip');
  const reachable = await target.evaluate((element, attribute) => {
    for (let node: HTMLElement | null = element as HTMLElement; node; node = node.parentElement) {
      if (node.tabIndex >= 0) {
        node.setAttribute(attribute, '');
        return true;
      }
    }
    return false;
  }, KEYBOARD_STOP_ATTRIBUTE);
  if (!reachable) return 'truncated, and neither it nor anything around it is in the tab order';

  const stop = page.locator(`[${KEYBOARD_STOP_ATTRIBUTE}]`);
  try {
    await page.keyboard.press('Shift');
    await stop.focus();
    try {
      await expect(tooltip).toHaveText(fullText, { timeout: 2_000 });
    } catch {
      return 'truncated, and keyboard focus does not open a tooltip with the full text';
    }
    await page.keyboard.press('Escape');
    try {
      await expect(tooltip).toHaveCount(0, { timeout: 2_000 });
    } catch {
      return 'truncated, and Escape does not close its tooltip';
    }
    return null;
  } finally {
    await stop.evaluate((element, attribute) => {
      (element as HTMLElement).blur();
      element.removeAttribute(attribute);
    }, KEYBOARD_STOP_ATTRIBUTE);
    await expect(tooltip).toHaveCount(0);
  }
}

// The page's `TruncatingTooltip` texts, by what the keyboard should do with each, and what is wrong.
export interface TruncationTabStops {
  fits: number;
  standalone: number;
  nested: number;
  findings: string[];
}

/*
 * Every `TruncatingTooltip` on screen (`data-truncating-tooltip`), held to its tab-stop contract: text
 * that fits is NOT a tab stop (it has nothing to reveal); cut text is one, unless something around it
 * already is — then it must not be, since a focusable inside a link or a button is a nested, empty
 * extra stop (axe's `nested-interactive`). "Something around it is a stop" is the browser's
 * `tabIndex >= 0`, not the component's own selector, so the check does not borrow the logic it checks.
 */
export async function checkTruncationTabStops(page: Page): Promise<TruncationTabStops> {
  return page.evaluate(() => {
    const result = { fits: 0, standalone: 0, nested: 0, findings: [] as string[] };
    document.querySelectorAll<HTMLElement>('[data-truncating-tooltip]').forEach((el) => {
      if (el.getClientRects().length === 0) return;
      const text = (el.textContent ?? '').trim();
      let insideStop = false;
      for (let node = el.parentElement; node; node = node.parentElement) {
        if (node.tabIndex >= 0) insideStop = true;
      }
      if (el.scrollWidth <= el.clientWidth) {
        result.fits += 1;
        if (el.tabIndex >= 0) result.findings.push(`"${text}" fits, and is still a tab stop`);
      } else if (insideStop) {
        result.nested += 1;
        if (el.tabIndex >= 0)
          result.findings.push(`"${text}" is a tab stop nested inside another tab stop`);
      } else {
        result.standalone += 1;
        if (el.tabIndex < 0)
          result.findings.push(`"${text}" is truncated, and the keyboard cannot reach it`);
      }
    });
    return result;
  });
}
