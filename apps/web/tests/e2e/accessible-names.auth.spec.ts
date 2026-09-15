import { expect, test, type Page } from '@playwright/test';

import { ROUTES } from '@/config/routes';

/*
 * The runtime half of the a11y sweep, and the half no static check can reach.
 *
 * `tests/unit/accessible-names.test.ts` reads source and proves the two lists agree — that no call site
 * passes a literal, that every UI label is declared, translated and wired. What it cannot see is whether
 * any of that arrives in a rendered page: `RowActionButton` could stop deriving its `aria-label` from
 * `tooltip`, `UiLabelsProvider` could merge its defaults OVER the app's translations instead of under
 * them, and the root layout could pass a label the provider never reads. Each of those leaves every
 * source file exactly as the structural guards demand, and every accessible name in English.
 *
 * So the assertions here are about the DOM, and the Spanish pass is the load-bearing one: an English
 * name matches the hardcoded string it replaced, which is precisely the failure. Only the second locale
 * distinguishes "translated" from "happened to already be in English".
 */

const COPY = {
  en: {
    search: 'Search expenses...',
    add: 'Add expense',
    clear: 'Clear',
    pagination: 'Pagination',
    previousPage: 'Go to previous page',
    nextPage: 'Go to next page',
    close: 'Close',
    sidebarTitle: 'Sidebar',
  },
  es: {
    search: 'Buscar gastos...',
    add: 'Agregar gasto',
    clear: 'Limpiar',
    pagination: 'Paginación',
    previousPage: 'Ir a la página anterior',
    nextPage: 'Ir a la página siguiente',
    close: 'Cerrar',
    sidebarTitle: 'Menú lateral',
  },
};

async function useLocale(page: Page, locale: 'en' | 'es') {
  // The app reads the locale from this cookie, not only from the stored user setting.
  await page
    .context()
    .addCookies([{ name: 'NEXT_LOCALE', value: locale, domain: 'localhost', path: '/' }]);
}

test.describe('accessible names (signed in)', () => {
  for (const locale of ['en', 'es'] as const) {
    test(`the names @repo/ui renders itself are in ${locale}`, async ({ page }) => {
      // Radix's own warning for a dialog with no description, which is otherwise console-only.
      const warnings: string[] = [];
      page.on('console', (message) => {
        if (message.text().includes('Missing `Description`')) warnings.push(message.text());
      });

      await useLocale(page, locale);
      await page.goto(ROUTES.expenses);

      /*
       * A row action's tooltip IS its accessible name — asserted as an equality between two things read
       * from the page rather than against a string, so it states the rule instead of a sample of it.
       *
       * Run under BOTH locales because only the Spanish one discriminates: the English tooltip for this
       * button is the word "Delete", which is exactly the hardcoded label the sweep removed, so an
       * English-only assertion passes on the defect it exists to catch. Proven by reintroducing
       * `aria-label="Delete"` — the English pass stays green and the Spanish one fails.
       */
      const action = page.getByTestId('expense-delete').first();
      await expect(action).toBeVisible();

      /*
       * Opening the tooltip is RETRIED as a whole — the interaction, not only the assertion.
       *
       * The button is server-rendered with its `aria-label` and `data-state="closed"` already in the
       * HTML, so it is visible and actionable before React has hydrated and attached Radix's pointer
       * handler. A hover sent in that window is simply dropped: the element never changes state, and
       * waiting longer on the attribute cannot help because no timer was ever started. On a warm dev
       * server the gap is invisible; on the first run after an idle one it failed both locales.
       * Re-entering the pointer each attempt is what recovers, hence `toPass` around the pair.
       */
      await expect(async () => {
        await page.mouse.move(0, 0);
        await action.hover();
        await expect(action).toHaveAttribute('aria-describedby', /./, { timeout: 1000 });
      }).toPass({ timeout: 20000 });
      // Radix puts the tooltip's text in a visually-hidden node, so this reads what a screen reader is
      // handed — which `getByRole('tooltip')` cannot see, the visible content being a separate node.
      const tooltipId = await action.getAttribute('aria-describedby');
      const name = await action.getAttribute('aria-label');
      expect(name).toBeTruthy();
      expect(name).toBe((await page.locator(`[id="${tooltipId}"]`).textContent())?.trim());

      // And it is a real keyboard stop, not a hover-only affordance.
      await action.press('Shift+Tab');
      await page.keyboard.press('Tab');
      await expect(action).toBeFocused();

      // The search field's accessible name is its placeholder — it has no visible label anywhere.
      const search = page.getByRole('textbox', { name: COPY[locale].search });
      await expect(search).toBeVisible();

      // Filling it reveals the clear button, whose label comes from the package, not the call site.
      await search.fill('zzz');
      await expect(page.getByRole('button', { name: COPY[locale].clear })).toBeVisible();
      await search.fill('');

      const pager = page.getByRole('navigation', { name: COPY[locale].pagination });
      await expect(pager).toBeVisible();
      // Both arrows, and not only the landmark: they are two labels from one context, and swapping
      // them survives every check that asks whether the pager is merely named.
      await expect(pager.getByRole('link', { name: COPY[locale].previousPage })).toBeVisible();
      await expect(pager.getByRole('link', { name: COPY[locale].nextPage })).toBeVisible();

      /*
       * Two dialogs, because the sweep gave them opposite answers and only one of each proves it.
       *
       * The entry form has nothing to add beyond its title, so it carries `aria-describedby={undefined}`
       * — Radix then drops the attribute entirely, where an omission would have left it warning.
       */
      await page.getByRole('button', { name: COPY[locale].add }).click();
      const form = page.getByRole('dialog');
      await expect(form).toBeVisible();
      await expect(form.getByRole('button', { name: COPY[locale].close })).toBeVisible();
      await expect(form).not.toHaveAttribute('aria-describedby', /./);
      await page.keyboard.press('Escape');
      await expect(form).toBeHidden();

      // The delete confirm does have something to say, so its description is a real, translated line.
      await page.getByTestId('expense-delete').first().click();
      const confirm = page.getByRole('dialog');
      await expect(confirm).toBeVisible();
      const describedBy = await confirm.getAttribute('aria-describedby');
      expect(describedBy, 'the confirm lost its description').toBeTruthy();
      expect((await page.locator(`[id="${describedBy}"]`).textContent())?.trim()).toBeTruthy();
      await page.keyboard.press('Escape');
      await expect(confirm).toBeHidden();

      /*
       * The mobile sidebar is a Sheet, so it is a dialog and needs a name and a description of its own
       * — and it is the one surface in this sweep that only exists below the md breakpoint. There is no
       * visible trigger for it anywhere in the app; `SidebarProvider` registers Ctrl/Cmd+B, which is how
       * a person opens it and therefore how this does.
       */
      await page.setViewportSize({ width: 390, height: 780 });
      /*
       * Reload after the resize. `useIsMobile` updates from a media-query EVENT, so a keypress sent in
       * the same tick still reaches the desktop branch and toggles the collapsed rail instead of
       * opening the sheet — a race that fails once in a handful of runs and reads as a broken feature.
       * Mounting at the mobile width settles it before anything is pressed.
       */
      await page.reload();
      await page.keyboard.press('ControlOrMeta+b');
      const sidebar = page.locator('[data-slot=sidebar][data-mobile=true]');
      await expect(sidebar).toBeVisible();
      await expect(sidebar).toHaveAccessibleName(COPY[locale].sidebarTitle);
      await expect(sidebar).toHaveAccessibleDescription(/\S/);

      expect(warnings, 'Radix warned about a dialog with no description').toEqual([]);
    });
  }
});
