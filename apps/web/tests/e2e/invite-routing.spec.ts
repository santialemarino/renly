import { expect, test } from '@playwright/test';

// Route literals mirror apps/web/config/routes.ts. Kept local so this spec stays self-contained and
// free of build-time path-alias resolution under Playwright's loader.
const LOGIN = '/login';
const SIGNUP = '/signup';
const ADMIN = '/admin';

// Verifies the invite-only access gate for logged-out visitors. Assumes the default SIGNUP_MODE=invite
// (the launch default); in `open` mode /signup would show the normal form instead.
test.describe('invite-only access gate (logged out)', () => {
  test('signup without an invite shows the invite-only notice and no registration form', async ({
    page,
  }) => {
    await page.goto(SIGNUP);

    await expect(page.getByTestId('invite-only-notice')).toBeVisible();
    // No registration form to submit — an uninvited visitor can't even enter a password (anti-enumeration).
    await expect(page.locator('input[type="password"]')).toHaveCount(0);
  });

  test('an invalid invite token still shows the invite-only notice (no leak, no form)', async ({
    page,
  }) => {
    await page.goto(`${SIGNUP}?invite=not-a-real-token`);

    await expect(page.getByTestId('invite-only-notice')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toHaveCount(0);
  });

  test('the admin page redirects logged-out visitors to login', async ({ page }) => {
    await page.goto(ADMIN);

    await page.waitForURL((url) => url.pathname === LOGIN);
    expect(new URL(page.url()).pathname).toBe(LOGIN);
  });
});
