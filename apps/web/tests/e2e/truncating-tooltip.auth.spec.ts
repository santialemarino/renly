import { expect, request as playwrightRequest, test, type Page } from '@playwright/test';

import { API_BASE, apiToken } from './helpers/api';
import { testMarker } from './helpers/factories';
import { expectRingContrast, measureRing, tabTo } from './helpers/focus';

/*
 * A truncated text's tooltip is reachable from the keyboard, not only by hover (WCAG 2.1.1), and
 * behaves as content on focus must (1.4.13): `TruncatingTooltip` makes the text a tab stop only while
 * it is cut, Radix opens the tooltip on that focus, and Escape dismisses it. Text that fits is not a
 * stop, and a touch press still opens nothing.
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

async function openExpenses(page: Page) {
  await page.setViewportSize(DESKTOP);
  await page.goto(EXPENSES);
  await expect(note(page, longNote)).toBeVisible({ timeout: 20_000 });
  await expect(note(page, shortNote)).toBeVisible();
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

    await page.keyboard.press('Escape');
    await expect(tooltip).toHaveCount(0);
    // Dismissed, not moved away from: focus stays on the note (1.4.13 "dismissible").
    expect(await cut.evaluate((el) => el === document.activeElement)).toBe(true);
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

  test('a press on a cut note opens no tooltip', async ({ page }) => {
    await openExpenses(page);
    await note(page, longNote).tap();
    await page.waitForTimeout(500);
    await expect(page.getByRole('tooltip')).toHaveCount(0);
  });
});
