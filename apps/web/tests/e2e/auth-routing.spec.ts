import { expect, test } from '@playwright/test';

// Route literals mirror apps/web/config/routes.ts. Kept local so this first e2e spec stays
// self-contained and free of build-time path-alias resolution under Playwright's loader.
const LOGIN = '/login';
const LANDING = '/';
const PROTECTED_PATH = '/investments';
const UNKNOWN_PATH = '/this-route-does-not-exist';

// Verifies the proxy gate is route-precise for logged-out visitors: only known protected routes
// bounce to login, unknown paths render the 404, and the 404 CTA returns to the landing page.
test.describe('auth routing (logged out)', () => {
  test('an unknown path renders the 404 page instead of redirecting to login', async ({ page }) => {
    const response = await page.goto(UNKNOWN_PATH);

    expect(response?.status()).toBe(404);
    await expect(page.getByTestId('not-found')).toBeVisible();
    expect(new URL(page.url()).pathname).toBe(UNKNOWN_PATH);
  });

  test('a protected path redirects to login, remembering where it was going', async ({ page }) => {
    await page.goto(`${PROTECTED_PATH}?page=2`);

    await page.waitForURL((url) => url.pathname === LOGIN);
    const url = new URL(page.url());
    expect(url.pathname).toBe(LOGIN);
    // Signing in follows it back (safeNextPath validates it on /login).
    expect(url.searchParams.get('next')).toBe(`${PROTECTED_PATH}?page=2`);
  });

  test('the 404 call-to-action returns to the landing page', async ({ page }) => {
    await page.goto(UNKNOWN_PATH);
    await expect(page.getByTestId('not-found')).toBeVisible();

    await page.getByTestId('not-found-home-cta').click();

    await page.waitForURL((url) => url.pathname === LANDING);
    expect(new URL(page.url()).pathname).toBe(LANDING);
  });
});
