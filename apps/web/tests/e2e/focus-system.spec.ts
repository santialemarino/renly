import { expect, test } from '@playwright/test';

import { expectRingContrast, measureRing, tabTo } from './helpers/focus';

// Route literals mirror apps/web/config/routes.ts, like every spec's.
const LANDING = '/';
const LOGIN = '/login';

/*
 * The focus system on the signed-OUT surfaces: the public layout's skip link, the neutral ring as the
 * auth form and the public header draw it, and the password toggle's keyboard cue. The signed-in half
 * (the protected layout, every overlay's focus return) is `focus-system.auth.spec.ts`.
 */
test.describe('focus system (signed out)', () => {
  test('the first Tab on a public page is the skip link, and it lands in main', async ({
    page,
  }) => {
    await page.goto(LANDING);
    const skip = page.getByTestId('skip-link');

    // Hidden until focused: present for a keyboard, invisible to everyone else.
    await expect(skip).toHaveCount(1);
    expect((await skip.boundingBox())?.width ?? 0).toBeLessThanOrEqual(1);

    await page.keyboard.press('Tab');
    await expect(skip).toBeFocused();
    expect((await skip.boundingBox())?.width ?? 0).toBeGreaterThan(40);

    await page.keyboard.press('Enter');
    await expect(page.locator('main')).toBeFocused();
    // The jump moved focus without leaving a fragment in the address (and a history entry behind it).
    expect(new URL(page.url()).hash).toBe('');

    // And the next stop is the page's own content, not the header that was skipped.
    await page.keyboard.press('Tab');
    expect(
      await page.evaluate(() => document.querySelector('main')?.contains(document.activeElement)),
    ).toBe(true);
  });

  test('the neutral ring clears 3:1 where the auth form and the public header draw it', async ({
    page,
  }) => {
    await page.goto(LOGIN);
    const email = page.getByTestId('login-email-input');
    await tabTo(page, email);
    // The Input's ring is on its wrapper (`focus-within`), the element that owns the border.
    expectRingContrast(await measureRing(email.locator('xpath=..')));

    await page.goto(LANDING);
    // The header's outline "Log in" link-button: the base Button, neutral variant.
    const login = page.locator(`header a[href="${LOGIN}"]`);
    await tabTo(page, login);
    expect(await login.evaluate((element) => element.matches(':focus-visible'))).toBe(true);
    expectRingContrast(await measureRing(login));
  });

  test('the password toggle’s keyboard cue is not its hover cue', async ({ page }) => {
    await page.goto(LOGIN);
    const password = page.getByTestId('login-password-input');
    const toggle = password.locator('xpath=..').locator('button[aria-pressed]');
    const icon = toggle.locator('span').first();

    // What each state paints: the button's own transform and the icon wrapper's animation.
    const state = async () => ({
      // Tailwind v4's `scale-*` sets the `scale` property, not `transform`.
      scale: await toggle.evaluate((element) => getComputedStyle(element).scale),
      animation: await icon.evaluate((element) => getComputedStyle(element).animationName),
    });

    await tabTo(page, toggle);
    expect(await toggle.evaluate((element) => element.matches(':focus-visible'))).toBe(true);
    const focused = await state();
    // The focus-bump idiom: the icon plays the bump, the button itself does not grow.
    expect(focused.animation).toBe('focus-bump');
    expect(focused.scale).toBe('none');

    await page.keyboard.press('Tab');
    await toggle.hover();
    await expect.poll(async () => (await state()).scale).toBe('1.1');
    const hovered = await state();
    expect(hovered.animation).toBe('none');

    expect(focused).not.toEqual(hovered);
  });
});
