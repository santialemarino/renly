import { expect, request as playwrightRequest, test } from '@playwright/test';

import { API_BASE, apiToken } from './helpers/api';
import { testMarker } from './helpers/factories';
import { measureIconTextRows } from './helpers/optical-centring';
import { waitForPageContent } from './helpers/text-clipping';

/*
 * Text beside an icon sits optically centred on it, and a link inside a hint takes the hint's size.
 *
 * Every icon + text row is `flex items-center`, which centres the label's line box on the icon; the
 * app font's vertical metrics are overridden (`lib/fonts/plus-jakarta-sans.ts`) so that the letters'
 * optical middle is where that box's middle is. With the face's own metrics every label drew low —
 * measured 1.0-1.5px at 14px, 0.9px at 16px, 1.9px at 24px, about 1px on average over these pages.
 *
 * The browser rounds each baseline to a whole pixel, and how it rounds depends on the platform's font
 * stack, so one row can land up to about a pixel off even with the right metrics (a 12.8px button
 * measured 0.70px high on macOS and 0.84px high on Linux CI). So each row is held to ROW_TOLERANCE_PX,
 * which catches a row that is really off, and the rows together to MEAN_TOLERANCE_PX, which catches the
 * font drawing everything low again: right metrics average about 0.25px, the face's own about 1px.
 *
 * Kept from passing vacuously: every page must render its own content and show rows, and the run must
 * meet each size the app's rows come in (`REQUIRED_SIZES`: the 12px field hints, the 12.8px small
 * buttons, the 14px controls and the 16px sidebar), so a page that changed shape cannot drop a size
 * out of the check unnoticed. The rows are found on the page, not listed (`helpers/optical-centring.ts`).
 */

// The pages: the sidebar on every one, the 12px field hints (/preferences), the small buttons (/data),
// the snapshot badges (/snapshots), a concept hint and the account rows (/accounts, seeded below).
const ROUTES = ['/dashboard', '/accounts', '/preferences', '/data', '/snapshots'] as const;
const ROW_TOLERANCE_PX = 1;
const MEAN_TOLERANCE_PX = 0.5;
const REQUIRED_SIZES = [12, 12.8, 14, 16];

// The concept hint /accounts shows once there is an account (`DismissableHint` derives the test id).
const RECONCILE_HINT_KEY = 'accounts-reconcile-hint-dismissed';

let cleanup: (() => Promise<void>) | undefined;

test.beforeAll(async () => {
  const token = await apiToken();
  const request = await playwrightRequest.newContext();
  const headers = { Authorization: `Bearer ${token}` };
  const settings = await (await request.get(`${API_BASE}/settings`, { headers })).json();
  const created = await request.post(`${API_BASE}/accounts`, {
    headers,
    data: {
      name: testMarker('optical'),
      type: 'bank',
      currency: settings.primary_currency ?? 'ARS',
      opening_balance: '100',
      opening_date: new Date().toISOString().slice(0, 10),
    },
  });
  expect(created.ok(), `POST /accounts: ${created.status()} ${await created.text()}`).toBe(true);
  const id: number = (await created.json()).id;
  cleanup = async () => {
    await request.delete(`${API_BASE}/accounts/${id}`, { headers });
    await request.dispose();
  };
});

test.afterAll(async () => {
  await cleanup?.();
});

test.beforeEach(async ({ page }) => {
  // A hint dismissed by an earlier run stays hidden; this spec needs it on screen.
  await page.addInitScript((key) => localStorage.removeItem(key), RECONCILE_HINT_KEY);
  await page.setViewportSize({ width: 1280, height: 1000 });
});

test('text beside an icon sits optically centred on it', async ({ page }) => {
  const failures: string[] = [];
  const sizes = new Set<number>();
  const offsets: number[] = [];
  for (const route of ROUTES) {
    await page.goto(route);
    expect(await waitForPageContent(page), `${route}: its own content never rendered`).toBe(true);
    await expect(page.getByTestId('not-found').or(page.getByTestId('error-boundary'))).toHaveCount(
      0,
    );
    await page.evaluate(() => document.fonts.ready);

    const rows = await measureIconTextRows(page);
    expect(rows.length, `${route}: no icon + text rows found`).toBeGreaterThan(0);
    for (const row of rows) {
      sizes.add(row.fontSize);
      offsets.push(Math.abs(row.offset));
      if (Math.abs(row.offset) > ROW_TOLERANCE_PX) {
        failures.push(
          `${route}: "${row.label}" (${row.fontSize}px) sits ${Math.abs(row.offset)}px ${row.offset > 0 ? 'low' : 'high'}`,
        );
      }
    }
  }

  expect(failures).toEqual([]);
  const mean = offsets.reduce((sum, offset) => sum + offset, 0) / offsets.length;
  console.log(
    `${offsets.length} icon + text rows at ${[...sizes].sort((a, b) => a - b).join(', ')}px, ` +
      `${mean.toFixed(2)}px off their icon on average`,
  );
  expect(mean, 'the rows sit off their icons on average').toBeLessThanOrEqual(MEAN_TOLERANCE_PX);
  for (const size of REQUIRED_SIZES) {
    expect([...sizes], `no ${size}px row was measured`).toContain(size);
  }
});

test('a link inside a hint takes the hint text size', async ({ page }) => {
  await page.goto('/accounts');
  const hint = page.getByTestId(`hint-${RECONCILE_HINT_KEY}`);
  await expect(hint).toBeVisible();
  const link = hint.getByRole('link');
  await expect(link).toHaveCount(1);

  const sizes = await link.evaluate((element) => {
    const text = element.closest('p');
    if (!text) throw new Error('the hint link is not inside the hint text');
    const of = (node: Element) => {
      const style = getComputedStyle(node);
      return { fontSize: style.fontSize, lineHeight: style.lineHeight };
    };
    return { link: of(element), text: of(text) };
  });
  expect(sizes.link).toEqual(sizes.text);
});
