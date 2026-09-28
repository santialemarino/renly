import { expect, test, type Page } from '@playwright/test';

import type { Clipping } from './helpers/overflow';
import {
  findClippedText,
  isAllowedTruncation,
  MIN_VISIBLE_EM,
  tooltipShowsFullText,
} from './helpers/text-clipping';

/*
 * The text sweep's rule, pinned case by case against pages built to break each clause — so the rule
 * is tested as the browser applies it (computed styles, real layout), not as a class name reads.
 *
 * Every case is one 120px box holding a text far longer than it, so each fixture CAN clip; the case is
 * what the page does about it. The tooltip is a stand-in with Radix's DOM contract: a trigger marked
 * `data-slot="tooltip-trigger"`, and on hover a `role="tooltip"` element holding the text.
 */

const LONG = 'Tarjeta Visa Signature del Banco de la Provincia de Buenos Aires';

// A page with one probe case inside a 120px card, and a stand-in tooltip wired to every trigger.
async function render(page: Page, body: string): Promise<void> {
  await page.setContent(`<!doctype html>
    <html><head><style>
      body { font: 14px sans-serif; margin: 20px; }
      .card { width: 120px; }
      .clip { overflow: hidden; }
      .truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .flex { display: flex; }
      .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
    </style></head>
    <body><div class="card">${body}</div>
    <script>
      document.querySelectorAll('[data-slot="tooltip-trigger"]').forEach((trigger) => {
        trigger.addEventListener('mouseenter', () => {
          const text = trigger.dataset.tooltipText;
          if (text === undefined) return;
          const tip = document.createElement('div');
          tip.setAttribute('role', 'tooltip');
          tip.textContent = text;
          tip.style.cssText = 'position:fixed;left:300px;top:300px';
          document.body.appendChild(tip);
        });
        trigger.addEventListener('mouseleave', () =>
          document.querySelectorAll('[role="tooltip"]').forEach((tip) => tip.remove()),
        );
      });
    </script></body></html>`);
}

// The one clipping on the page, with the matched count so a case cannot pass on an empty page.
async function onlyClipping(page: Page): Promise<Clipping | null> {
  const report = await findClippedText(page);
  expect(report.matched).toBeGreaterThan(0);
  expect(report.clipped.length).toBeLessThanOrEqual(1);
  return report.clipped[0] ?? null;
}

test.describe('what counts as an allowed truncation', () => {
  test('an ellipsis with a title carrying the whole text is allowed', async ({ page }) => {
    await render(page, `<div class="truncate" title="${LONG}">${LONG}</div>`);
    const clipping = await onlyClipping(page);
    expect(clipping).toMatchObject({ ownBoxOnly: true, ellipsis: true, cue: 'title' });
    expect(clipping!.visibleEm).toBeGreaterThanOrEqual(MIN_VISIBLE_EM);
    expect(isAllowedTruncation(clipping!)).toBe(true);
  });

  test('a title on an ancestor counts, since the browser shows it over the text', async ({
    page,
  }) => {
    await render(page, `<div title="${LONG}"><div class="truncate">${LONG}</div></div>`);
    expect(isAllowedTruncation((await onlyClipping(page))!)).toBe(true);
  });

  test('an ellipsis with no cue is a finding', async ({ page }) => {
    await render(page, `<div class="truncate">${LONG}</div>`);
    const clipping = await onlyClipping(page);
    expect(clipping).toMatchObject({ ellipsis: true, cue: null });
    expect(isAllowedTruncation(clipping!)).toBe(false);
  });

  test('an aria-label is not a cue — it reaches no sighted reader', async ({ page }) => {
    await render(page, `<div class="truncate" aria-label="${LONG}">${LONG}</div>`);
    expect(isAllowedTruncation((await onlyClipping(page))!)).toBe(false);
  });

  test('a title with different text is not a cue', async ({ page }) => {
    await render(page, `<div class="truncate" title="Tarjeta Visa">${LONG}</div>`);
    const clipping = await onlyClipping(page);
    expect(clipping?.cue).toBeNull();
    expect(isAllowedTruncation(clipping!)).toBe(false);
  });

  test('a hard clip with no ellipsis is a finding, title or not', async ({ page }) => {
    await render(
      page,
      `<div class="clip" style="white-space: nowrap" title="${LONG}">${LONG}</div>`,
    );
    const clipping = await onlyClipping(page);
    expect(clipping).toMatchObject({ ellipsis: false, cue: 'title' });
    expect(isAllowedTruncation(clipping!)).toBe(false);
  });

  test('truncate on a flex container draws no ellipsis, so it is a finding', async ({ page }) => {
    await render(page, `<div class="truncate flex" title="${LONG}">${LONG}</div>`);
    const clipping = await onlyClipping(page);
    expect(clipping?.ellipsis).toBe(false);
    expect(isAllowedTruncation(clipping!)).toBe(false);
  });

  test('a truncation whose own box is cut off by its card is a finding', async ({ page }) => {
    // The truncating box is 200px inside a 120px card that clips: its ellipsis is never drawn.
    await render(
      page,
      `<div class="clip"><div class="truncate" style="width: 200px" title="${LONG}">${LONG}</div></div>`,
    );
    const clipping = await onlyClipping(page);
    expect(clipping).toMatchObject({ ellipsis: true, cue: 'title', ownBoxOnly: false });
    expect(isAllowedTruncation(clipping!)).toBe(false);
  });

  test('a truncation squeezed to a few letters is a finding, cue or not', async ({ page }) => {
    // 28px at 14px is 2em: an ellipsis and a letter or two. The same text in the 120px card passes.
    await render(page, `<div class="truncate" style="width: 28px" title="${LONG}">${LONG}</div>`);
    const clipping = await onlyClipping(page);
    expect(clipping).toMatchObject({ ownBoxOnly: true, ellipsis: true, cue: 'title' });
    expect(clipping!.visibleEm).toBeLessThan(MIN_VISIBLE_EM);
    expect(isAllowedTruncation(clipping!)).toBe(false);
  });

  test('text that fits is not clipped at all', async ({ page }) => {
    await render(page, `<div class="truncate">Visa</div>`);
    expect(await onlyClipping(page)).toBeNull();
  });

  test('visually hidden text is not measured', async ({ page }) => {
    await render(page, `<span class="sr-only">${LONG}</span><p>Visa</p>`);
    const report = await findClippedText(page);
    expect(report).toMatchObject({ matched: 1, clipped: [] });
  });

  test('text in a nested inline element is measured where it is laid out', async ({ page }) => {
    await render(page, `<div class="clip" style="white-space: nowrap"><b>${LONG}</b></div>`);
    const clipping = await onlyClipping(page);
    expect(clipping?.text).toBe(LONG);
    expect(clipping?.reason).toMatch(/cut off horizontally/);
  });
});

test.describe('a tooltip cue is only a claim until it is opened', () => {
  test('a tooltip that shows the whole text is allowed', async ({ page }) => {
    await render(
      page,
      `<div class="truncate" data-slot="tooltip-trigger" data-tooltip-text="${LONG}">${LONG}</div>`,
    );
    const clipping = (await onlyClipping(page))!;
    expect(clipping.cue).toBe('tooltip');
    expect(isAllowedTruncation(clipping)).toBe(true);
    expect(await tooltipShowsFullText(page, clipping)).toBe(true);
  });

  test('a trigger that opens nothing fails', async ({ page }) => {
    await render(page, `<div class="truncate" data-slot="tooltip-trigger">${LONG}</div>`);
    const clipping = (await onlyClipping(page))!;
    expect(isAllowedTruncation(clipping)).toBe(true);
    expect(await tooltipShowsFullText(page, clipping)).toBe(false);
  });

  test('a tooltip with other text fails', async ({ page }) => {
    await render(
      page,
      `<div class="truncate" data-slot="tooltip-trigger" data-tooltip-text="Tarjeta">${LONG}</div>`,
    );
    const clipping = (await onlyClipping(page))!;
    expect(await tooltipShowsFullText(page, clipping)).toBe(false);
  });
});
