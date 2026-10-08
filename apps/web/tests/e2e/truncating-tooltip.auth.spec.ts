import {
  expect,
  request as playwrightRequest,
  test,
  type Locator,
  type Page,
} from '@playwright/test';

import { API_BASE, apiToken } from './helpers/api';
import { testMarker } from './helpers/factories';
import { expectRingContrast, measureRing, tabTo } from './helpers/focus';

/*
 * A truncated text's tooltip is reachable from the keyboard, not only by hover (WCAG 2.1.1), and
 * behaves as content on focus must (1.4.13): `TruncatingTooltip` makes the text a tab stop only while
 * it is cut, Radix opens the tooltip on that focus, and Escape dismisses it. Text that fits is not a
 * stop, the tooltip is never open over text that is not cut, and a touch press opens nothing — not
 * even for a frame.
 *
 * The text sweep (`locale-text-clipping.auth.spec.ts`) holds every page to the same contract through
 * the DOM; this spec walks it with real Tab presses on one table, and paints the ring. The rows are two
 * expenses the spec writes and removes itself: a note far longer than its 12rem cell, and one that fits.
 */

const EXPENSES = '/expenses';
const DESKTOP = { width: 1280, height: 900 };
// The sidebar, the header and the toolbar come before the table; a generous bound on the walk.
const MAX_TAB_STOPS = 200;

let longNote: string;
let shortNote: string;
let cleanup: () => Promise<void>;

test.beforeAll(async () => {
  const marker = testMarker('truncating-tooltip');
  longNote = `${marker} nota larga del gasto que no entra en la celda de la tabla de gastos`;
  shortNote = marker.slice(-6);
  const token = await apiToken();
  const request = await playwrightRequest.newContext();
  const headers = { Authorization: `Bearer ${token}` };
  const settings = await (await request.get(`${API_BASE}/settings`, { headers })).json();
  const ids: number[] = [];
  for (const notes of [longNote, shortNote]) {
    const created = await request.post(`${API_BASE}/expenses`, {
      headers,
      data: {
        date: new Date().toISOString().slice(0, 10),
        amount: '1.00',
        currency: settings.primary_currency ?? 'ARS',
        category: 'other',
        notes,
        payment_method: 'cash',
      },
    });
    expect(created.ok(), `POST /expenses: ${created.status()} ${await created.text()}`).toBe(true);
    ids.push((await created.json()).id);
  }
  cleanup = async () => {
    for (const id of ids) await request.delete(`${API_BASE}/expenses/${id}`, { headers });
    await request.dispose();
  };
});

test.afterAll(async () => {
  await cleanup?.();
});

// A note cell by its whole text: the short note is the tail of the long one's marker.
function note(page: Page, text: string) {
  return page.locator('[data-truncating-tooltip]', { hasText: new RegExp(`^${text}$`) });
}

// Whether an element is the focused one.
const isFocused = (locator: Locator) => locator.evaluate((el) => el === document.activeElement);
const isCut = (locator: Locator) => locator.evaluate((el) => el.scrollWidth > el.clientWidth);

async function openExpenses(page: Page) {
  await page.setViewportSize(DESKTOP);
  await page.goto(EXPENSES);
  await expect(note(page, longNote)).toBeVisible({ timeout: 20_000 });
  await expect(note(page, shortNote)).toBeVisible();
  // Hydrated and measured: the cut note is a stop. A hover or a press before that reaches no handler.
  await expect(note(page, longNote)).toHaveAttribute('tabindex', '0');
}

test.describe('a truncated text is reachable from the keyboard', () => {
  test('Tab reaches the cut note, opens its tooltip and paints the ring; Escape closes it', async ({
    page,
  }) => {
    await openExpenses(page);
    const cut = note(page, longNote);
    // The fixture really is cut: otherwise the stop below would be correctly absent.
    expect(await cut.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);

    await tabTo(page, cut, MAX_TAB_STOPS);
    // The row actions Tab passed on the way have tooltips of their own; let their exits finish.
    const tooltip = page.getByRole('tooltip');
    await expect(tooltip).toHaveCount(1);
    await expect(tooltip).toHaveText(longNote);
    expectRingContrast(await measureRing(cut));
    /*
     * Radix points the trigger's `aria-describedby` at an open tooltip; the component strips it, since
     * the whole text is already in the DOM and a description would have it read twice.
     */
    await expect(cut).not.toHaveAttribute('aria-describedby');

    await page.keyboard.press('Escape');
    await expect(tooltip).toHaveCount(0);
    // Dismissed, not moved away from: focus stays on the note (1.4.13 "dismissible").
    expect(await isFocused(cut)).toBe(true);
  });

  test('a focused note that stops being cut keeps focus until it leaves, then drops its stop', async ({
    page,
  }) => {
    await openExpenses(page);
    const cut = note(page, longNote);
    await tabTo(page, cut, MAX_TAB_STOPS);
    const tooltip = page.getByRole('tooltip');
    await expect(tooltip).toHaveCount(1);
    await expect(tooltip).toHaveText(longNote);

    // The same resize a wider window gives: the note's text now fits its box.
    await cut.evaluate((el) => ((el as HTMLElement).style.fontSize = '1px'));
    await expect.poll(() => isCut(cut)).toBe(false);
    await expect(tooltip).toHaveCount(0);
    expect(await isFocused(cut)).toBe(true);
    expect(await cut.evaluate((el) => el.tabIndex)).toBe(0);

    await page.keyboard.press('Tab');
    expect(await isFocused(cut)).toBe(false);
    await expect.poll(() => cut.evaluate((el) => el.tabIndex)).toBe(-1);
  });

  test('a hover over a note that fits leaves nothing to open once it is cut', async ({ page }) => {
    await openExpenses(page);
    const fits = note(page, shortNote);
    const tooltip = page.getByRole('tooltip');
    await fits.hover();
    // Rested on, as a reader's pointer would: long enough for any open it asks for to be decided.
    await page.waitForTimeout(300);
    await expect(tooltip).toHaveCount(0);
    await page.mouse.move(0, 0);
    await page.mouse.move(1, 1);

    // The same resize a narrower window gives: the note is cut now, with the pointer long gone.
    await fits.evaluate((el) => ((el as HTMLElement).style.maxWidth = '1ch'));
    await expect.poll(() => isCut(fits)).toBe(true);
    await page.waitForTimeout(500);
    await expect(tooltip).toHaveCount(0);
    // The note does have a tooltip to give now: a fresh hover opens it.
    await fits.hover();
    await expect(tooltip).toHaveText(shortNote);
  });

  test('a focusable scroll region around the table does not take the note’s stop', async ({
    page,
  }) => {
    await openExpenses(page);
    const cut = note(page, longNote);
    /*
     * What `Table` does while it is wider than its column: its scroll container becomes a focusable,
     * named region. It is not a control, so the cut note inside it stays a stop of its own, and the
     * region's own focus opens no tooltip. The note is narrowed a little so it measures again.
     */
    const region = page.locator('[data-slot="table-container"]').filter({ has: cut });
    await region.evaluate((el) => {
      el.setAttribute('tabindex', '0');
      el.setAttribute('role', 'region');
      el.setAttribute('aria-label', 'Gastos');
    });
    await cut.evaluate((el) => ((el as HTMLElement).style.maxWidth = '10rem'));
    await expect
      .poll(() => cut.evaluate((el) => el.getBoundingClientRect().width))
      .toBeLessThanOrEqual(160);
    await expect.poll(() => cut.evaluate((el) => el.tabIndex)).toBe(0);

    await page.keyboard.press('Shift');
    await region.focus();
    expect(await isFocused(region)).toBe(true);
    await page.waitForTimeout(500);
    await expect(page.getByRole('tooltip')).toHaveCount(0);
  });

  test('a note that fits is not a tab stop', async ({ page }) => {
    await openExpenses(page);
    const fits = note(page, shortNote);
    expect(await fits.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
    // Walk the page's whole tab order once, top to bottom, marking every element it stops on.
    await page.evaluate(() =>
      document.addEventListener('focusin', (event) =>
        (event.target as Element).setAttribute('data-was-focused', ''),
      ),
    );
    for (let stop = 0; stop < MAX_TAB_STOPS; stop += 1) {
      await page.keyboard.press('Tab');
      if (await page.evaluate(() => document.activeElement === document.body)) break;
    }
    // The walk really went past the note: the delete action in its own row was a stop.
    const row = page.getByRole('row').filter({ has: fits });
    await expect(row.getByTestId('expense-delete')).toHaveAttribute('data-was-focused');
    await expect(fits).not.toHaveAttribute('data-was-focused');
    expect(await fits.evaluate((el) => el.tabIndex)).toBe(-1);
  });
});

/*
 * A cut label inside a control (a filter's trigger button, a nav link) must not become a second tab
 * stop nested in it; the control's own KEYBOARD focus opens the tooltip instead, and a mouse click on
 * it does not. No label in the app is cut at this width, so the first filter's label is narrowed to
 * 3rem — the component measures the real box, so this is the same state a long Spanish label reaches.
 */
test.describe('a truncated text inside a button', () => {
  async function narrowFilterLabel(page: Page) {
    await openExpenses(page);
    const trigger = page.getByTestId('filter-combobox-trigger').first();
    const label = trigger.locator('[data-truncating-tooltip]');
    const fullLabel = (await label.textContent()) ?? '';
    await label.evaluate((el) => ((el as HTMLElement).style.maxWidth = '3rem'));
    await expect.poll(() => label.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
    return { trigger, label, fullLabel };
  }

  test('is not a stop of its own; the button’s keyboard focus opens its tooltip', async ({
    page,
  }) => {
    const { trigger, label, fullLabel } = await narrowFilterLabel(page);
    expect(await label.evaluate((el) => el.tabIndex)).toBe(-1);

    await tabTo(page, trigger, MAX_TAB_STOPS);
    const tooltip = page.getByRole('tooltip');
    await expect(tooltip).toHaveCount(1);
    await expect(tooltip).toHaveText(fullLabel);

    await page.keyboard.press('Escape');
    await expect(tooltip).toHaveCount(0);
    expect(await trigger.evaluate((el) => el === document.activeElement)).toBe(true);
    // One Tab leaves the button for the next control: the label was never a stop between them.
    await page.keyboard.press('Tab');
    expect(await label.evaluate((el) => el === document.activeElement)).toBe(false);
  });

  test('a mouse press on the button, away from the label, opens no tooltip', async ({ page }) => {
    const { trigger } = await narrowFilterLabel(page);
    const box = (await trigger.boundingBox())!;
    /*
     * Pressed at the chevron's end, so the pointer never hovers the label, and held: the press is what
     * focuses the button, and releasing it would open the filter's popover, which takes focus away.
     */
    await page.mouse.move(box.x + box.width - 8, box.y + box.height / 2);
    await page.mouse.down();
    expect(await trigger.evaluate((el) => el === document.activeElement)).toBe(true);
    await page.waitForTimeout(500);
    await expect(page.getByRole('tooltip')).toHaveCount(0);
    await page.mouse.up();
  });
});

test.describe('on a touch screen', () => {
  test.use({ hasTouch: true });

  test('a press on a cut note opens no tooltip, not even for a frame', async ({ page }) => {
    await openExpenses(page);
    const cut = note(page, longNote);
    /*
     * A tooltip that opens on the tap's focus and closes on its click lives ~140ms: gone again before
     * a final count could see it. Every tooltip ever mounted is recorded instead.
     */
    await page.evaluate(() => {
      const record = window as unknown as { tooltipsSeen: number };
      record.tooltipsSeen = 0;
      const content = '[data-slot="tooltip-content"]';
      new MutationObserver((mutations) => {
        for (const mutation of mutations)
          for (const node of mutation.addedNodes)
            if (node instanceof Element && (node.matches(content) || node.querySelector(content)))
              record.tooltipsSeen += 1;
      }).observe(document.body, { childList: true, subtree: true });
    });
    await cut.tap();
    // The press did focus the note, so the focus path a flash would come from really ran.
    expect(await isFocused(cut)).toBe(true);
    await page.waitForTimeout(500);
    await expect(page.getByRole('tooltip')).toHaveCount(0);
    expect(
      await page.evaluate(() => (window as unknown as { tooltipsSeen: number }).tooltipsSeen),
    ).toBe(0);
  });
});
