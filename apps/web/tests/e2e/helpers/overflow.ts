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
 * clip counts: text taller than a box that is not clipping it is drawn in full. And a box that is 0×0
 * — BOTH sides zero — and does not clip is not a box the text was laid out in: Recharts'
 * `ResponsiveContainer` wraps every chart in one so it can measure its parent, and every axis label
 * "ran out" of it while being drawn in full. A box with ONE side zero is a real box: a flex item
 * squeezed to no width by a sibling that will not shrink, or a zero-height wrapper, still has text
 * running out of it.
 *
 * Positions are read from a Range over the element's contents, i.e. from the laid-out TEXT, not from
 * the element's box — a clipped element's box is exactly as wide as the clip, which is the problem.
 * The one exception is an element that clips ITSELF (`overflow: hidden` on the element, which is what
 * `truncate` sets): what runs past its own edge is not drawn at all, so it cannot also escape an
 * ancestor. That overflow is reported once, on each axis the element clips — "wider than its own box",
 * "taller than its own box" — and the ancestor walk carries on with the part that IS drawn — so a truncated name whose own box is inside its card reports only
 * its own truncation, and one whose box is itself cut off by the card reports both.
 *
 * Each finding also says HOW the text is cut, for callers that allow a deliberate truncation (see
 * `helpers/text-clipping.ts`): whether the element itself draws an ellipsis, and whether the page
 * offers the full text some other way.
 */

// How the page offers the full text of a cut-off element: the nearest `title` (the browser shows an
// ancestor's title over its descendants too), or a Radix tooltip trigger (self or ancestor) — which
// is only a CLAIM until the tooltip is opened and read, since a trigger can open nothing.
export type FullTextCue = 'title' | 'tooltip' | null;

export interface Clipping {
  // Position among the matched elements, and the text the reader was meant to see.
  index: number;
  text: string;
  reason: string;
  // The only failure is the element's own box: nothing around it cuts it or is overprinted.
  ownBoxOnly: boolean;
  // The element truncates its own text with a visible ellipsis: a block container (not flex or grid,
  // where `text-overflow` draws nothing) that clips on X, does not wrap, and sets `text-overflow:
  // ellipsis` — what Tailwind's `truncate` produces on a block.
  ellipsis: boolean;
  cue: FullTextCue;
  // How much of the text the element's own box shows, in ems of its own font size: a 14px name in a
  // 28px box shows 2em — about two letters.
  visibleEm: number;
}

export interface FindClippingOptions {
  // When set, every clipped element gets this attribute with its `index` as the value (and any left
  // from an earlier call is removed first), so a caller can find it again — `[attr="3"]` — to hover it.
  markAttribute?: string;
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
export async function findClipping(
  page: Page,
  selector: string,
  options: FindClippingOptions = {},
): Promise<ClippingReport> {
  return page.evaluate(
    ({ selector, tolerance, markAttribute }) => {
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

      const clips = (value: string) => value === 'hidden' || value === 'clip';
      const normalize = (value: string) => value.replace(/\s+/g, ' ').trim();

      if (markAttribute) {
        document
          .querySelectorAll(`[${markAttribute}]`)
          .forEach((el) => el.removeAttribute(markAttribute));
      }

      const elements = [...document.querySelectorAll(selector)].filter(
        (el) => el.getClientRects().length > 0 && el.checkVisibility({ visibilityProperty: true }),
      );
      const clipped: {
        index: number;
        text: string;
        reason: string;
        ownBoxOnly: boolean;
        ellipsis: boolean;
        cue: 'title' | 'tooltip' | null;
        visibleEm: number;
      }[] = [];

      elements.forEach((el, index) => {
        const range = document.createRange();
        range.selectNodeContents(el);
        const measured = range.getBoundingClientRect();
        if (measured.width === 0 && measured.height === 0) return;
        const text = {
          left: measured.left,
          right: measured.right,
          top: measured.top,
          bottom: measured.bottom,
        };
        const reasons: string[] = [];
        const own = getComputedStyle(el);

        const ownBox = hasBox(el) && el.scrollWidth > el.clientWidth + tolerance;
        if (ownBox) {
          reasons.push(`wider than its own box (${el.scrollWidth}px > ${el.clientWidth}px)`);
        }
        // Vertically only a real clip counts, as for ancestors: the clamp below hides it from the walk,
        // so it is reported here.
        if (hasBox(el) && clips(own.overflowY) && el.scrollHeight > el.clientHeight + tolerance) {
          reasons.push(`taller than its own box (${el.scrollHeight}px > ${el.clientHeight}px)`);
        }
        // What an element clips itself is not drawn, so only the drawn part can escape further out.
        if (hasBox(el)) {
          const box = paddingBox(el);
          if (clips(own.overflowX)) {
            text.left = Math.max(text.left, box.left);
            text.right = Math.min(text.right, box.right);
          }
          if (clips(own.overflowY)) {
            text.top = Math.max(text.top, box.top);
            text.bottom = Math.min(text.bottom, box.bottom);
          }
        }

        let walkX = true;
        let walkY = true;
        for (let ancestor = el.parentElement; ancestor && (walkX || walkY); ) {
          if (hasBox(ancestor)) {
            const style = getComputedStyle(ancestor);
            const box = paddingBox(ancestor);
            const clipsX = clips(style.overflowX);
            const clipsY = clips(style.overflowY);
            // A scroller: what lies past its edge is reachable, so nothing from here out is a finding.
            if (!clipsX && style.overflowX !== 'visible') walkX = false;
            if (!clipsY && style.overflowY !== 'visible') walkY = false;
            // A non-clipping 0×0 box holds nothing in it (see above).
            const empty = !clipsX && box.right - box.left === 0 && box.bottom - box.top === 0;
            if (
              walkX &&
              !empty &&
              (text.right > box.right + tolerance || text.left < box.left - tolerance)
            ) {
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
          const display = own.display;
          const ellipsis =
            hasBox(el) &&
            !/flex|grid/.test(display) &&
            clips(own.overflowX) &&
            own.textOverflow === 'ellipsis' &&
            (own.whiteSpace === 'nowrap' || own.textWrapMode === 'nowrap');
          const fullText = normalize(el.textContent ?? '');
          const titled = el.closest('[title]');
          const cue =
            titled && normalize(titled.getAttribute('title') ?? '') === fullText
              ? 'title'
              : el.closest('[data-slot="tooltip-trigger"]')
                ? 'tooltip'
                : null;
          if (markAttribute) el.setAttribute(markAttribute, String(index));
          clipped.push({
            index,
            text: el.textContent ?? '',
            reason: reasons.join('; '),
            ownBoxOnly: ownBox && reasons.length === 1,
            ellipsis,
            cue,
            visibleEm: hasBox(el) ? el.clientWidth / parseFloat(own.fontSize) : 0,
          });
        }
      });

      return { matched: elements.length, clipped };
    },
    { selector, tolerance: TOLERANCE_PX, markAttribute: options.markAttribute ?? null },
  );
}

/*
 * The steady-state answer: measures after `settle`, and re-measures for a short while if anything is
 * clipped, because a layout still converging (a legend whose measured height is catching up with a
 * reflow) is not a defect. A clipping that survives the whole budget is.
 *
 * `isFinding` narrows what counts as "anything clipped" for that retry — a caller that allows some
 * clippings (a deliberate truncation) would otherwise wait out the whole budget on every page that has
 * one. The report still lists every clipping; the caller judges them.
 */
export async function findSettledClipping(
  page: Page,
  selector: string,
  budgetMs = 3_000,
  isFinding: (clipping: Clipping) => boolean = () => true,
  options: FindClippingOptions = {},
): Promise<ClippingReport> {
  const deadline = Date.now() + budgetMs;
  for (;;) {
    await settle(page);
    const report = await findClipping(page, selector, options);
    if (!report.clipped.some(isFinding) || Date.now() > deadline) return report;
    await page.waitForTimeout(200);
  }
}
