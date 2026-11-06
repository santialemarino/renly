import { expect, request as playwrightRequest, test, type Page } from '@playwright/test';

import { API_BASE, apiToken } from './helpers/api';
import { tabTo } from './helpers/focus';
import { waitForHydration } from './helpers/hydration';

/*
 * The snapshots grid is ONE tab stop, the arrows move through its cells, and a focused cell opens on
 * the keyboard what its tooltips show a pointer (the shares, the change since the last snapshot), in
 * either language. Enter opens the cell's snapshot, and closing the dialog returns focus to the cell.
 *
 * The holding is one row per account under a fixed name, found again and unarchived by every run and
 * archived afterwards — the API can archive an investment but never delete one (the money seed does
 * the same). Its two snapshots are on fixed dates of the current and the previous month, and the API
 * keeps one per date, so a re-run rewrites them instead of adding more. The page is filtered to it by
 * its name.
 */

const HOLDING = 'e2e-grid-keyboard-holding';
const SNAPSHOTS = `/snapshots?search=${HOLDING}`;
// English on a desktop; Spanish on a phone, where the move to a cell scrolls the grid past its sticky
// columns — a scroll Radix would otherwise close the cell's hint on.
const VIEWPORTS = { en: { width: 1280, height: 900 }, es: { width: 390, height: 844 } } as const;
// The sidebar, the header and the toolbar come before the grid; a generous bound on the walk.
const MAX_TAB_STOPS = 80;
const COPY = {
  en: {
    shares: '12,345.5 shares',
    change: 'Change since the previous snapshot',
    earlier: '10 shares',
  },
  es: {
    shares: '12.345,5 acciones',
    change: 'Variación desde el snapshot anterior',
    earlier: '10 acciones',
  },
} as const;

let cleanup: () => Promise<void>;

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

test.beforeAll(async () => {
  const token = await apiToken();
  const request = await playwrightRequest.newContext();
  const headers = { Authorization: `Bearer ${token}` };
  const listed = await request.get(
    `${API_BASE}/investments?active_only=false&page_size=100&search=${HOLDING}`,
    { headers },
  );
  expect(listed.ok(), `GET /investments: ${listed.status()}`).toBe(true);
  const body = await listed.json();
  const rows: { id: number; name: string }[] = Array.isArray(body) ? body : body.items;
  let id = rows.find((row) => row.name === HOLDING)?.id;
  if (id === undefined) {
    const created = await request.post(`${API_BASE}/investments`, {
      headers,
      data: { name: HOLDING, category: 'stocks', base_currency: 'USD' },
    });
    expect(created.ok(), `POST /investments: ${created.status()}`).toBe(true);
    id = (await created.json()).id as number;
  } else {
    const unarchived = await request.patch(`${API_BASE}/investments/${id}/unarchive`, { headers });
    expect(unarchived.ok(), `PATCH unarchive: ${unarchived.status()}`).toBe(true);
  }
  const today = new Date();
  const lastMonth = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), 0));
  const thisMonth = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), 1));
  for (const [date, value, quantity] of [
    [lastMonth, '100', '10'],
    [thisMonth, '125', '12345.5'],
  ] as const) {
    const snapshot = await request.post(`${API_BASE}/investments/${id}/snapshots`, {
      headers,
      data: { date: isoDate(date), value, quantity, currency: 'USD' },
    });
    expect(snapshot.ok(), `POST snapshot: ${snapshot.status()} ${await snapshot.text()}`).toBe(
      true,
    );
  }
  cleanup = async () => {
    await request.patch(`${API_BASE}/investments/${id}/archive`, { headers });
    await request.dispose();
  };
});

test.afterAll(async () => {
  await cleanup?.();
});

// Whether the focused element is inside the grid.
const focusInGrid = (page: Page) =>
  page.evaluate(() => document.activeElement?.closest('[role="grid"]') !== null);

// An OPEN tooltip saying `text`: a closing one stays in the DOM through its exit animation.
const openTooltip = (page: Page, text: string) =>
  page
    .locator('[data-slot="tooltip-content"]:not([data-state="closed"])')
    .filter({ hasText: text });

for (const locale of ['en', 'es'] as const) {
  test(`the grid is one stop the arrows move through (${locale})`, async ({ page, context }) => {
    await context.addCookies([
      { name: 'NEXT_LOCALE', value: locale, domain: 'localhost', path: '/' },
    ]);
    await page.setViewportSize(VIEWPORTS[locale]);
    await page.goto(SNAPSHOTS);
    const grid = page.getByRole('grid');
    const row = grid.getByRole('row').filter({ hasText: HOLDING });
    await expect(row).toBeVisible({ timeout: 20_000 });
    const sort = grid.getByRole('columnheader').first().getByRole('button');
    await waitForHydration(sort);

    // Tab lands on the grid's first cell, and the next Tab leaves the grid: it is one stop.
    await tabTo(page, sort, MAX_TAB_STOPS);
    await page.keyboard.press('Tab');
    expect(await focusInGrid(page)).toBe(false);
    await page.keyboard.press('Shift+Tab');
    await expect(sort).toBeFocused();

    // Down to the holding's row (past any section header), then along it.
    const name = row.getByRole('gridcell').first();
    for (let step = 0; step < 4; step += 1) {
      if (await name.evaluate((el) => el === document.activeElement)) break;
      await page.keyboard.press('ArrowDown');
    }
    await expect(name).toBeFocused();
    await page.keyboard.press('End');
    await expect(row.getByRole('gridcell').last().getByRole('button')).toBeFocused();

    // The last month's cell: the shares and the change open on focus, with no pointer anywhere.
    await page.keyboard.press('ArrowLeft');
    const cell = row.getByRole('gridcell').nth(-2);
    await expect(cell).toBeFocused();
    expect(await cell.evaluate((el) => el.matches(':focus-visible'))).toBe(true);
    // The row action's own tooltip may still be fading out, so the cell's is found by what it says.
    const tooltip = openTooltip(page, COPY[locale].shares);
    await expect(tooltip).toHaveCount(1);
    await expect(tooltip).toContainText(COPY[locale].change);
    await expect(cell).toHaveAccessibleDescription(new RegExp(COPY[locale].shares));

    // One more to the left: on the phone the grid scrolls it out from under the sticky name column,
    // and its hint holds through the scroll (scroll events land a frame later, so let them), until
    // Escape dismisses it without moving focus (WCAG 1.4.13). Home is the row's first cell again.
    await page.keyboard.press('ArrowLeft');
    const earlier = row.getByRole('gridcell').nth(1);
    await expect(earlier).toBeFocused();
    const earlierTip = openTooltip(page, COPY[locale].earlier);
    await expect(earlierTip).toHaveCount(1);
    await page.evaluate(
      () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
    );
    await expect(earlierTip).toHaveCount(1);
    await page.keyboard.press('Escape');
    await expect(earlierTip).toHaveCount(0);
    await expect(earlier).toBeFocused();
    await page.keyboard.press('Home');
    await expect(name).toBeFocused();

    // Enter opens the cell's snapshot; Escape closes it and focus is back on the cell.
    await page.keyboard.press('End');
    await page.keyboard.press('ArrowLeft');
    await page.keyboard.press('Enter');
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(cell).toBeFocused();
  });
}
