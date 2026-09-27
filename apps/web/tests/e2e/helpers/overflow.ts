import type { Page } from '@playwright/test';

/*
 * The overflow harness: finds every element matching a selector whose text the reader cannot fully
 * see. General on purpose — the money sweep uses it for `[data-money]`, and any other "this text must
 * never be cut off" rule (Spanish copy running out of its button, a legend name) is the same question
 * with a different selector.
 *
 * "Cannot fully see" is three separate failures, and each is checked on its own because each one alone
 * passes the other two:
 *
 *   * the element is a box and its content is wider than it — `scrollWidth > clientWidth`, which is
 *     also what a `truncate` ellipsis looks like from the outside;
 *   * the text runs out of a box AROUND it and prints over whatever is beside it. A figure in a flex
 *     row that cannot shrink is exactly as wide as its text, so it never overflows itself — the row,
 *     and the card around the row, are what it escapes. Measured on the pre-fix dashboard: at 1024px
 *     "-3,923,637.12" ran out of its card and over the next one, with every own-box check passing;
 *   * an ancestor with `overflow: hidden` / `clip` cuts the text off. This is the one that turned
 *     5,296,553.12 into "5,296,553.": the figure in the last card ran past it and the page's
 *     `<main className="overflow-x-hidden">` hid the tail, with no ellipsis to say a digit was missing.
 *
 * A SCROLL container (`auto` / `scroll`) is not a clip: content past its edge is one scroll away, which
 * is how a wide table is meant to behave. So on each axis the walk up the ancestors stops at the first
 * scroll container — anything beyond it is about the scroller, not the text. Vertically only a real
 * clip counts: text taller than a box that is not clipping it is drawn in full.
 *
 * Positions are read from a Range over the element's contents, i.e. from the laid-out TEXT, not from
 * the element's box — a clipped element's box is exactly as wide as the clip, which is the problem.
 */

export interface Clipping {
  // Position among the matched elements, and the text the reader was meant to see.
  index: number;
  text: string;
  reason: string;
}

export interface ClippingReport {
  // How many visible elements matched the selector — so a caller can tell "nothing was clipped" from
  // "nothing was there".
  matched: number;
  clipped: Clipping[];
}

// Sub-pixel layout rounding, not overflow.
const TOLERANCE_PX = 1;

// Waits for web fonts, every finite animation and transition, and two frames — measuring mid-animation
// reads a layout the reader never sees at rest.
export async function settle(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await document.fonts.ready;
    const finite = document
      .getAnimations()
      .filter((animation) => animation.effect?.getComputedTiming().endTime !== Infinity);
    await Promise.all(finite.map((animation) => animation.finished.catch(() => undefined)));
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
  });
}

// One measurement of every visible element matching `selector`.
export async function findClipping(page: Page, selector: string): Promise<ClippingReport> {
  return page.evaluate(
    ({ selector, tolerance }) => {
      const label = (el: Element) => {
        const classes =
          typeof el.className === 'string' ? el.className.trim().split(/\s+/).slice(0, 4) : [];
        return [el.tagName.toLowerCase(), ...classes].join('.');
      };
      // Inline and `contents` elements have no box of their own for text to escape.
      const hasBox = (el: Element) => {
        const display = getComputedStyle(el).display;
        return display !== 'inline' && display !== 'contents';
      };
      // The padding box, in viewport coordinates — where content stops being drawn.
      const paddingBox = (el: Element) => {
        const rect = el.getBoundingClientRect();
        const left = rect.left + el.clientLeft;
        const top = rect.top + el.clientTop;
        return { left, top, right: left + el.clientWidth, bottom: top + el.clientHeight };
      };

      const elements = [...document.querySelectorAll(selector)].filter(
        (el) => el.getClientRects().length > 0 && el.checkVisibility({ visibilityProperty: true }),
      );
      const clipped: { index: number; text: string; reason: string }[] = [];

      elements.forEach((el, index) => {
        const range = document.createRange();
        range.selectNodeContents(el);
        const text = range.getBoundingClientRect();
        if (text.width === 0 && text.height === 0) return;
        const reasons: string[] = [];

        if (hasBox(el) && el.scrollWidth > el.clientWidth + tolerance) {
          reasons.push(`wider than its own box (${el.scrollWidth}px > ${el.clientWidth}px)`);
        }

        let walkX = true;
        let walkY = true;
        for (let ancestor = el.parentElement; ancestor && (walkX || walkY); ) {
          if (hasBox(ancestor)) {
            const style = getComputedStyle(ancestor);
            const box = paddingBox(ancestor);
            const clipsX = style.overflowX === 'hidden' || style.overflowX === 'clip';
            const clipsY = style.overflowY === 'hidden' || style.overflowY === 'clip';
            // A scroller: what lies past its edge is reachable, so nothing from here out is a finding.
            if (!clipsX && style.overflowX !== 'visible') walkX = false;
            if (!clipsY && style.overflowY !== 'visible') walkY = false;
            if (walkX && (text.right > box.right + tolerance || text.left < box.left - tolerance)) {
              reasons.push(
                clipsX
                  ? `cut off horizontally by ${label(ancestor)}`
                  : `runs out of ${label(ancestor)}`,
              );
              // One escape is the finding; every ancestor outside it would repeat it.
              walkX = false;
            }
            if (
              walkY &&
              clipsY &&
              (text.bottom > box.bottom + tolerance || text.top < box.top - tolerance)
            ) {
              reasons.push(`cut off vertically by ${label(ancestor)}`);
              walkY = false;
            }
          }
          ancestor = ancestor.parentElement;
        }

        if (reasons.length > 0) {
          clipped.push({ index, text: el.textContent ?? '', reason: reasons.join('; ') });
        }
      });

      return { matched: elements.length, clipped };
    },
    { selector, tolerance: TOLERANCE_PX },
  );
}

/*
 * The steady-state answer: measures after `settle`, and re-measures for a short while if anything is
 * clipped, because a layout still converging (a legend whose measured height is catching up with a
 * reflow) is not a defect. A clipping that survives the whole budget is.
 */
export async function findSettledClipping(
  page: Page,
  selector: string,
  budgetMs = 3_000,
): Promise<ClippingReport> {
  const deadline = Date.now() + budgetMs;
  for (;;) {
    await settle(page);
    const report = await findClipping(page, selector);
    if (report.clipped.length === 0 || Date.now() > deadline) return report;
    await page.waitForTimeout(200);
  }
}
