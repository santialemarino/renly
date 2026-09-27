import { expect, test, type Page } from '@playwright/test';

import { ROUTES } from '@/config/routes';

/*
 * A protected page whose read fails renders the app's own error boundary: inside the shell, in the
 * reader's language, with a retry that actually retries.
 *
 * Before this boundary existed, the same failure replaced the whole app with Next's hardcoded-English
 * "Application error" screen — no nav, no retry, an empty <title>, in Spanish too. Every static check
 * passes on that state, because nothing is MISSING from the source that a scan could look for; the
 * only way to see it is to make a server read fail and look at the page.
 *
 * The failure is a real one, not a test hook: `/expenses` forwards `date_from` to the API, which
 * refuses a value that is not a date with a 422, and `getExpenses` throws on any non-2xx — the
 * shared `if (!res.ok) throw` every `lib/api` module carries. Playwright cannot intercept that request
 * (it is made by the Next server, not the browser), which is why the failure is driven through input.
 */

const BROKEN = `${ROUTES.expenses}?date_from=not-a-date`;
const NAV = '[data-testid="sidebar-nav"]';

// Literal copy rather than the translation files, so a boundary rendering the wrong locale's strings
// — or a raw key path — cannot pass by agreeing with the file it read them from.
const COPY = {
  en: { title: 'Something went wrong', retry: 'Try again', expenses: 'Expenses' },
  es: { title: 'Algo salió mal', retry: 'Reintentar', expenses: 'Gastos' },
};

// A server render on a dev server can take well past Playwright's 5s default; see mobile-navigation.
const NAV_TIMEOUT = 20_000;

async function useLocale(page: Page, locale: 'en' | 'es') {
  await page
    .context()
    .addCookies([{ name: 'NEXT_LOCALE', value: locale, domain: 'localhost', path: '/' }]);
}

test.describe('error boundary (signed in)', () => {
  for (const locale of ['en', 'es'] as const) {
    test(`a failed page read renders the boundary inside the shell, in ${locale}`, async ({
      page,
    }) => {
      await useLocale(page, locale);
      await page.goto(BROKEN);

      const boundary = page.getByTestId('error-boundary');
      await expect(boundary).toBeVisible({ timeout: NAV_TIMEOUT });
      await expect(boundary.getByRole('heading', { level: 1 })).toHaveText(COPY[locale].title);
      await expect(boundary.getByRole('button', { name: COPY[locale].retry })).toBeVisible();

      // Still inside the app: the nav is there to leave by, and the document is still ours.
      await expect(page.locator(NAV)).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('lang', locale);
      expect((await page.title()).trim()).not.toBe('');
    });
  }

  test('retry asks the server again and renders the page once the read succeeds', async ({
    page,
  }) => {
    await useLocale(page, 'en');
    await page.goto(BROKEN);
    const boundary = page.getByTestId('error-boundary');
    await expect(boundary).toBeVisible({ timeout: NAV_TIMEOUT });

    /*
     * Make the next request for this page succeed WITHOUT navigating — a navigation would clear the
     * boundary by itself (Next resets it when the route changes), and then the retry would be proving
     * nothing. Next keeps its router in step with `history.replaceState`, so the retry's refresh asks
     * for `/expenses` while the boundary is still up, which is exactly a transient failure that has
     * since cleared. It tells apart both halves of the retry: without the refresh the boundary
     * re-renders the failed payload it already holds, and without the reset it stays up over the
     * fresh one.
     */
    await page.evaluate((path) => window.history.replaceState(null, '', path), ROUTES.expenses);
    await boundary.getByRole('button', { name: COPY.en.retry }).click();

    await expect(page.getByRole('heading', { level: 1, name: COPY.en.expenses })).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    await expect(boundary).toHaveCount(0);
  });
});
