import { expect, test, type Page } from '@playwright/test';

import { findClipping } from './helpers/overflow';
import { describeFinding, findClippedText, isAllowedTruncation } from './helpers/text-clipping';

/*
 * The overflow harness itself, pinned on static pages — through BOTH sweeps that use it: the money
 * sweep's `[data-money]` measurement and the text sweep's probe of every text element.
 *
 * Each case is a shape the harness once missed or could miss, and each must be reported by both paths.
 * They come from review: a harness change that skipped any box with ONE side zero, and one that stopped
 * reporting a vertical clip, both left #230's money sweep silent on a cut figure while every other
 * spec stayed green. The last case is the one layout the harness must NOT report — Recharts' 0×0
 * measuring wrapper, whose text is drawn in full.
 */

const FIGURE = '1.234.567,89 ARS';

async function render(page: Page, body: string): Promise<void> {
  await page.setContent(`<!doctype html>
    <html><head><style>
      body { font: 14px sans-serif; margin: 20px; }
      .truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      [data-money] { white-space: nowrap; }
    </style></head><body>${body}</body></html>`);
}

// The money sweep's finding for the one figure, and the text sweep's for the same text.
async function bothPaths(page: Page) {
  const money = await findClipping(page, '[data-money]');
  const text = await findClippedText(page);
  const textFindings = text.clipped.filter((clipping) => !isAllowedTruncation(clipping));
  return { money, text, textFindings };
}

const CUT_SHAPES: [string, string][] = [
  [
    'a figure in a flex item squeezed to no width by a sibling that will not shrink',
    `<div style="display: flex; width: 200px">
       <div style="flex: 1 1 0; min-width: 0"><span data-money>${FIGURE}</span></div>
       <div style="flex: 0 0 200px">sibling</div>
     </div>`,
  ],
  [
    'a figure in a 40px-wide wrapper with no height',
    `<div style="width: 40px; height: 0"><span data-money>${FIGURE}</span></div>`,
  ],
  [
    'a figure that clips itself to 10px of a 20px line, inside a 10px clip',
    `<div style="height: 10px; overflow: hidden">
       <span data-money style="display: block; overflow: hidden; height: 10px; line-height: 20px">${FIGURE}</span>
     </div>`,
  ],
];

for (const [name, body] of CUT_SHAPES) {
  test(`both sweeps report ${name}`, async ({ page }) => {
    await render(page, body);
    const { money, text, textFindings } = await bothPaths(page);
    expect(money.matched).toBe(1);
    expect(money.clipped.map((clipping) => clipping.text)).toEqual([FIGURE]);
    expect(text.matched).toBeGreaterThan(0);
    expect(textFindings.map((clipping) => clipping.text)).toContain(FIGURE);
  });
}

test('the text sweep reports a name squeezed beside a badge that will not shrink', async ({
  page,
}) => {
  // The payments-calendar row before the fix: a shrink-0 badge, then the name, then the figure — at a
  // phone's row width. The name carries a title, so only the squeeze can make it a finding.
  const name = 'e2e-money-1790538174097-ir61oi';
  await render(
    page,
    `<div style="display: flex; justify-content: space-between; gap: 12px; width: 330px">
       <div style="display: flex; min-width: 0; align-items: center; gap: 12px">
         <span style="flex-shrink: 0; white-space: nowrap; padding: 2px 8px">Vencimiento de tarjeta</span>
         <div style="display: flex; min-width: 0; flex-direction: column">
           <div class="truncate" title="${name}">${name}</div>
         </div>
       </div>
       <span data-money>${FIGURE}</span>
     </div>`,
  );
  const report = await findClippedText(page);
  const clipping = report.clipped.find((candidate) => candidate.text === name);
  expect(clipping, 'the squeezed name is reported').toBeDefined();
  expect(isAllowedTruncation(clipping!), describeFinding(clipping!)).toBe(false);
});

test('neither sweep reports text inside a 0×0 measuring wrapper', async ({ page }) => {
  await render(
    page,
    `<div style="width: 0; height: 0"><div style="width: 300px"><span data-money>${FIGURE}</span></div></div>`,
  );
  const { money, text } = await bothPaths(page);
  expect(money).toMatchObject({ matched: 1, clipped: [] });
  expect(text.clipped).toEqual([]);
});
