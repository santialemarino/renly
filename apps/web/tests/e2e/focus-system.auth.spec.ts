import { expect, request, test, type Locator, type Page } from '@playwright/test';

import { API_BASE, apiToken } from './helpers/api';
import { testMarker } from './helpers/factories';
import {
  expectFocusCueDiffersFromHover,
  expectRingContrast,
  measureRing,
  tabTo,
} from './helpers/focus';

// Route literals mirror apps/web/config/routes.ts, like every spec's.
const EXPENSES = '/expenses';
const SUBSCRIPTIONS = '/subscriptions';
const PHONE = { width: 390, height: 844 };
const DESKTOP = { width: 1280, height: 800 };

/*
 * The quick-add awaits six reads and preloads five chunks before it opens anything, and a dev server
 * compiles those chunks on the first open — the same measured budget `helpers/factories.ts` gives it.
 */
const QUICK_ADD_OPEN_MS = 20_000;

/*
 * Where focus goes when an overlay closes, for every KIND of overlay the app has.
 *
 * The defect: after Escape (or ✕, or Cancel) `document.activeElement` was <body> while the trigger was
 * still on the page, because Radix returns focus only to its own `Dialog.Trigger` and every dialog
 * here is controlled. The fix lives in the two base wrappers, so the cases below are one per PATH
 * into them rather than one per dialog: a plain controlled dialog closed three ways, a popover inside
 * it (Radix's own trigger path, which must keep working), a toolbar popover, the quick-add (whose
 * trigger disables itself while loading, so nothing holds focus when the dialog mounts), the quick-add
 * SWAP (the incoming form was opened from inside the outgoing one, which is gone by the time it
 * closes), a type-to-confirm delete (its input takes focus with `autoFocus`, which makes Radix skip its
 * open event) and the phone nav sheet (its hamburger sits outside any Dialog.Trigger).
 * `tests/unit/focus-system.test.ts` proves every Radix dialog in the codebase goes through those
 * wrappers; `use-return-focus.test.tsx` covers the chain logic case by case.
 */
test.describe('focus returns to what opened an overlay (signed in)', () => {
  const dialog = (page: Page) => page.getByRole('dialog');

  async function openAddExpense(page: Page): Promise<Locator> {
    const add = page.getByTestId('entity-list-add');
    await add.focus();
    await page.keyboard.press('Enter');
    await expect(dialog(page)).toBeVisible();
    return add;
  }

  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(DESKTOP);
  });

  test('a controlled dialog, closed by Escape, by ✕ and by Cancel', async ({ page }) => {
    await page.goto(EXPENSES);

    let add = await openAddExpense(page);
    await page.keyboard.press('Escape');
    await expect(dialog(page)).toHaveCount(0);
    await expect(add).toBeFocused();

    add = await openAddExpense(page);
    await dialog(page).locator('[data-slot="dialog-close"]').click();
    await expect(dialog(page)).toHaveCount(0);
    await expect(add).toBeFocused();

    add = await openAddExpense(page);
    await dialog(page).locator('[data-slot="dialog-footer"] [data-variant="outline"]').click();
    await expect(dialog(page)).toHaveCount(0);
    await expect(add).toBeFocused();
  });

  test('a popover inside a dialog returns to its trigger and leaves the dialog open', async ({
    page,
  }) => {
    await page.goto(EXPENSES);
    await openAddExpense(page);

    const combobox = dialog(page).locator('button[role="combobox"]').first();
    await combobox.focus();
    await page.keyboard.press('Enter');
    await expect(combobox).toHaveAttribute('aria-expanded', 'true');
    await page.keyboard.press('Escape');

    await expect(combobox).toHaveAttribute('aria-expanded', 'false');
    await expect(combobox).toBeFocused();
    await expect(dialog(page)).toBeVisible();
  });

  test('a toolbar popover returns to its trigger', async ({ page }) => {
    await page.goto(EXPENSES);
    const filter = page.getByTestId('filter-combobox-trigger').first();
    await filter.focus();
    await page.keyboard.press('Enter');
    await expect(filter).toHaveAttribute('aria-expanded', 'true');

    await page.keyboard.press('Escape');
    await expect(filter).toHaveAttribute('aria-expanded', 'false');
    await expect(filter).toBeFocused();
  });

  test('the quick-add, and a form it swapped in, return to the quick-add', async ({ page }) => {
    await page.goto(EXPENSES);
    const quickAdd = page.getByTestId('quick-add-trigger');

    await quickAdd.click();
    await expect(page.getByTestId('expense-form-notes')).toBeVisible({
      timeout: QUICK_ADD_OPEN_MS,
    });
    await page.keyboard.press('Escape');
    await expect(dialog(page)).toHaveCount(0);
    await expect(quickAdd).toBeFocused();

    await quickAdd.click();
    await expect(page.getByTestId('expense-form-notes')).toBeVisible({
      timeout: QUICK_ADD_OPEN_MS,
    });
    // The swap: the income form is opened from INSIDE the expense form, which then goes away.
    await dialog(page)
      .getByRole('radio', { name: /^(Income|Ingreso)$/ })
      .click();
    await expect(page.locator('form#income-form')).toBeVisible();
    await expect(page.getByTestId('expense-form-notes')).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(dialog(page)).toHaveCount(0);
    await expect(quickAdd).toBeFocused();
  });

  test('a type-to-confirm delete, which autofocuses its input, returns to the row’s Delete', async ({
    page,
  }) => {
    // Seeded through the API so the spec owns its row; the list is the subscriptions page, one of the
    // seven type-to-confirm deletes.
    const marker = testMarker('focus-type-to-confirm');
    const token = await apiToken();
    const api = await request.newContext({
      baseURL: API_BASE,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const created = await api.post('/subscriptions', {
      data: {
        name: marker,
        amount: '9.99',
        currency: 'USD',
        billing_cycle: 'monthly',
        next_billing_date: new Date().toISOString().slice(0, 10),
      },
    });
    expect(created.ok(), `seeding a subscription failed with ${created.status()}`).toBe(true);
    const { id } = (await created.json()) as { id: number };

    try {
      await page.goto(SUBSCRIPTIONS);
      // The row's last action is its Delete (the RowActionButton order is edit, archive, delete).
      const remove = page.getByRole('row').filter({ hasText: marker }).getByRole('button').last();
      const open = async () => {
        await remove.focus();
        await page.keyboard.press('Enter');
        // Premise: the dialog's own input took focus, the case Radix never reports as an open.
        await expect(dialog(page).locator('input#type-to-confirm')).toBeFocused();
      };

      await open();
      await page.keyboard.press('Escape');
      await expect(dialog(page)).toHaveCount(0);
      await expect(remove).toBeFocused();

      await open();
      await dialog(page).locator('[data-slot="dialog-footer"] [data-variant="outline"]').click();
      await expect(dialog(page)).toHaveCount(0);
      await expect(remove).toBeFocused();
    } finally {
      await api.delete(`/subscriptions/${id}`);
      await api.dispose();
    }
  });

  test('a clear button’s keyboard cue is not its hover cue', async ({ page }) => {
    // The search field's clear ✕, one of the four icon buttons that used to scale on focus exactly
    // as on hover. It only joins the tab order once the field has a value.
    await page.goto(EXPENSES);
    const search = page.locator('main [data-slot="input"]').first();
    await search.focus();
    await page.keyboard.type('x');
    const clear = search.locator('xpath=..').locator('button');
    await expect(clear).toHaveAttribute('tabindex', '0');
    await search.focus();
    await expectFocusCueDiffersFromHover(page, clear, clear.locator('svg'));
  });

  test.describe('below the breakpoint', () => {
    const TRIGGER = '[data-sidebar="trigger"]';
    const NAV = '[data-testid="sidebar-nav"]';

    test.beforeEach(async ({ page }) => {
      await page.setViewportSize(PHONE);
    });

    test('the nav sheet returns to the hamburger', async ({ page }) => {
      await page.goto(EXPENSES);
      const hamburger = page.locator(TRIGGER);
      await hamburger.click();
      await expect(page.locator(NAV)).toBeVisible();

      await page.keyboard.press('Escape');
      await expect(page.locator(NAV)).toHaveCount(0);
      await expect(hamburger).toBeFocused();
    });
  });
});

test.describe('the skip link (signed in)', () => {
  for (const viewport of [DESKTOP, PHONE]) {
    test(`is the first Tab stop and lands in main at ${viewport.width}px`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(EXPENSES);
      const skip = page.getByTestId('skip-link');

      await page.keyboard.press('Tab');
      await expect(skip).toBeFocused();
      expect((await skip.boundingBox())?.width ?? 0).toBeGreaterThan(40);

      await page.keyboard.press('Enter');
      await expect(page.locator('main')).toBeFocused();
      expect(new URL(page.url()).hash).toBe('');

      // One more Tab reaches the page's own first control — the whole sidebar was skipped.
      await page.keyboard.press('Tab');
      expect(
        await page.evaluate(() => document.querySelector('main')?.contains(document.activeElement)),
      ).toBe(true);
    });
  }
});

/*
 * The neutral ring as the app's own controls draw it: the search field (the Input wrapper's
 * `focus-within` ring), a toolbar filter (a hand-styled outline trigger) and a dialog's Cancel (the
 * base Button, on the dialog surface). Each measured against its real backdrop and every token surface.
 */
test('the neutral ring clears 3:1 on the app’s controls (signed in)', async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.goto(EXPENSES);

  const search = page.locator('main [data-slot="input"]').first();
  await tabTo(page, search);
  expectRingContrast(await measureRing(search.locator('xpath=..')));

  const filter = page.getByTestId('filter-combobox-trigger').first();
  await tabTo(page, filter);
  expect(await filter.evaluate((element) => element.matches(':focus-visible'))).toBe(true);
  expectRingContrast(await measureRing(filter));

  await page.getByTestId('entity-list-add').focus();
  await page.keyboard.press('Enter');
  const cancel = page
    .getByRole('dialog')
    .locator('[data-slot="dialog-footer"] [data-variant="outline"]');
  await tabTo(page, cancel);
  expect(await cancel.evaluate((element) => element.matches(':focus-visible'))).toBe(true);
  expectRingContrast(await measureRing(cancel));
});
