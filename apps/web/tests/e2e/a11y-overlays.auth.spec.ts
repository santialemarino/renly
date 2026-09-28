import { request } from '@playwright/test';

import { A11Y_LOCALES } from './helpers/a11y-routes';
import { API_BASE, apiToken } from './helpers/api';
import {
  expect,
  expectNoA11yViolations,
  openForScan,
  scanName,
  settleForScan,
  test,
} from './helpers/axe';
import { testMarker } from './helpers/factories';

/*
 * What the route sweep cannot see: the app's overlays OPEN, and the phone layout.
 *
 * A page scan runs on the page as it loads, so a dialog, a popover or the nav sheet is either absent
 * (unmounted until opened) or, once open, the only thing axe may look at — Radix hides the rest of
 * the page from assistive tech while it is up. So each overlay is opened and then scanned on its own
 * with `include()`: the quick-add dialog, a `FormCombobox` popover inside it, a type-to-confirm delete,
 * and the nav sheet. One of each KIND, because each base component is shared by every instance of its
 * kind. The phone is scanned only where its layout differs — the top bar with the hamburger, and the
 * sheet it opens — since every other page reflows the same components the desktop sweep already saw.
 */

// Route literals mirror apps/web/config/routes.ts, like every spec's. /snapshots rather than the
// dashboard, which auto-starts the welcome tour on an account that has not finished onboarding.
const START = '/snapshots';
const SUBSCRIPTIONS = '/subscriptions';
const PHONE = { width: 390, height: 844 };
const DESKTOP = { width: 1280, height: 900 };
const HAMBURGER = '[data-sidebar="trigger"]';
const NAV_SHEET = '[data-sidebar="sidebar"][data-mobile="true"]';
// The quick-add's first open awaits six reads and compiles its chunks on a dev server (see factories).
const QUICK_ADD_OPEN_MS = 20_000;

test.describe('accessibility of open overlays (signed in)', { tag: '@a11y' }, () => {
  for (const locale of A11Y_LOCALES) {
    test(`the quick-add dialog and a combobox popover inside it (${locale})`, async ({
      page,
      makeAxeBuilder,
    }, info) => {
      await page.setViewportSize(DESKTOP);
      await openForScan(page, START, locale);

      await page.getByTestId('quick-add-trigger').click();
      await expect(page.getByTestId('expense-form-notes')).toBeVisible({
        timeout: QUICK_ADD_OPEN_MS,
      });
      await settleForScan(page);
      await expectNoA11yViolations(
        page,
        await makeAxeBuilder().include('[role="dialog"]').analyze(),
        info,
        scanName('quick-add-dialog', locale),
        { wholePage: false },
      );

      const combobox = page.getByRole('dialog').locator('button[role="combobox"]').first();
      await combobox.click();
      await expect(combobox).toHaveAttribute('aria-expanded', 'true');
      await settleForScan(page);
      await expectNoA11yViolations(
        page,
        await makeAxeBuilder().include('[data-slot="popover-content"]').analyze(),
        info,
        scanName('form-combobox-popover', locale),
        { wholePage: false },
      );
    });

    test(`a type-to-confirm delete (${locale})`, async ({ page, makeAxeBuilder }, info) => {
      // Seeded through the API so the spec owns the row it opens the delete on.
      const marker = testMarker('a11y-type-to-confirm');
      const api = await request.newContext({
        baseURL: API_BASE,
        extraHTTPHeaders: { Authorization: `Bearer ${await apiToken()}` },
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
        await page.setViewportSize(DESKTOP);
        await openForScan(page, SUBSCRIPTIONS, locale);
        // The row's last action is its Delete (the RowActionButton order is edit, archive, delete).
        await page.getByRole('row').filter({ hasText: marker }).getByRole('button').last().click();
        await expect(page.getByRole('dialog').locator('input#type-to-confirm')).toBeFocused();
        await settleForScan(page);
        await expectNoA11yViolations(
          page,
          await makeAxeBuilder().include('[role="dialog"]').analyze(),
          info,
          scanName('type-to-confirm-dialog', locale),
          { wholePage: false },
        );
      } finally {
        await api.delete(`/subscriptions/${id}`);
        await api.dispose();
      }
    });

    test(`the phone layout and its nav sheet (${locale})`, async ({
      page,
      makeAxeBuilder,
    }, info) => {
      await page.setViewportSize(PHONE);
      await openForScan(page, START, locale);
      await expectNoA11yViolations(
        page,
        await makeAxeBuilder().analyze(),
        info,
        scanName('phone-page', locale),
        { wholePage: true },
      );

      /*
       * The hamburger is a disclosure: it says it is collapsed, names the sheet it controls, and says
       * it is expanded once that sheet is up — the sheet carrying exactly the id it named.
       */
      const hamburger = page.locator(HAMBURGER);
      await expect(hamburger).toHaveAttribute('aria-expanded', 'false');
      const controls = await hamburger.getAttribute('aria-controls');
      expect(controls, 'the hamburger names no element it controls').toBeTruthy();

      await hamburger.click();
      const sheet = page.locator(NAV_SHEET);
      await expect(sheet).toBeVisible();
      await expect(sheet).toHaveAttribute('id', controls ?? '');
      await expect(hamburger).toHaveAttribute('aria-expanded', 'true');
      await settleForScan(page);
      await expectNoA11yViolations(
        page,
        await makeAxeBuilder().include(NAV_SHEET).analyze(),
        info,
        scanName('nav-sheet', locale),
        { wholePage: false },
      );

      await page.keyboard.press('Escape');
      await expect(sheet).toHaveCount(0);
      await expect(hamburger).toHaveAttribute('aria-expanded', 'false');
    });
  }

  test('a table wider than its column is a named Tab stop the arrows scroll, and only then', async ({
    page,
  }) => {
    /*
     * `scrollable-region-focusable` only fires where a table overflows, so the page scans prove the
     * fix only on the pages that happen to overflow at their width. This pins the behaviour itself, on
     * the expenses table (the harness account always has a page of expenses): at a phone width it
     * overflows (the premise) and is then a focusable, named region whose columns the arrow keys
     * reach; at every width the Tab stop exists exactly when the overflow does.
     */
    const container = page.locator('[data-slot="table-container"]').first();
    const state = () =>
      container.evaluate((element) => ({
        overflows: element.scrollWidth > element.clientWidth,
        tabIndex: element.getAttribute('tabindex'),
        role: element.getAttribute('role'),
        name: element.getAttribute('aria-label'),
      }));

    await page.setViewportSize(PHONE);
    await openForScan(page, '/expenses', 'en');
    await expect(container).toHaveAttribute('data-overflowing', 'true');
    const phone = await state();
    expect(phone.overflows, 'premise: the expenses table overflows a phone').toBe(true);
    expect(phone).toMatchObject({ tabIndex: '0', role: 'region', name: 'Expenses' });

    await container.focus();
    const before = await container.evaluate((element) => element.scrollLeft);
    await page.keyboard.press('ArrowRight');
    await expect
      .poll(() => container.evaluate((element) => element.scrollLeft))
      .toBeGreaterThan(before);

    for (const width of [768, 1280, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      await expect
        .poll(async () => {
          const { overflows, tabIndex, role } = await state();
          return overflows === (tabIndex === '0') && overflows === (role === 'region');
        }, `the Tab stop and the overflow disagree at ${width}px`)
        .toBe(true);
    }
  });
});
