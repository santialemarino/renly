import { expect, request as playwrightRequest, test } from '@playwright/test';

import { API_BASE, apiToken } from './helpers/api';
import { expectNoA11yViolations, presetAxeBuilder, settleForScan } from './helpers/axe';
import { testMarker } from './helpers/factories';
import { waitForHydration } from './helpers/hydration';

// Route literals mirror apps/web/config/routes.ts, like every spec's.
const ACCOUNT = '/account';
const sharedGroup = (id: number) => `/shared/${id}`;

// A literal string as a pattern: the account name may hold regex metacharacters.
const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

interface GroupsUsingName {
  groups: { id: number; name: string }[];
}

/*
 * Renaming yourself from /account: the field opens on the name the API has now, a save reaches the
 * API, and a reload shows the new name rather than the one the session was signed in with.
 */
test('the account name can be changed from /account (signed in)', async ({ page }) => {
  const api = await playwrightRequest.newContext({
    baseURL: API_BASE,
    extraHTTPHeaders: { Authorization: `Bearer ${await apiToken()}` },
  });
  const original = ((await (await api.get('/auth/me')).json()) as { name: string }).name;
  const renamed = testMarker('name');
  try {
    await page.goto(ACCOUNT);
    const input = page.getByTestId('account-name-input');
    await expect(input).toHaveValue(original);
    await waitForHydration(input);

    // Blank is refused in the form, before anything is sent.
    await input.fill('   ');
    await page.getByTestId('account-name-submit').click();
    await expect(page.getByText('This field is required')).toBeVisible();

    await input.fill(renamed);
    await page.getByTestId('account-name-submit').click();
    await expect
      .poll(async () => ((await (await api.get('/auth/me')).json()) as { name: string }).name)
      .toBe(renamed);

    await page.reload();
    await expect(page.getByTestId('account-name-input')).toHaveValue(renamed);
  } finally {
    await api.patch('/me', { data: { name: original } });
    await api.dispose();
  }
});

/*
 * Bringing the groups along. The checkbox shows only once the name differs, counts and names the groups
 * still calling the user by the current name (not one where they go by a nickname), works from the
 * keyboard, and appears without the Save button jumping. A save with it ticked renames the seat, the
 * group hub shows the new name with a line in its activity, and the option is gone once the page has
 * the new name, with no flicker back.
 *
 * Two PATCHes in all, the rename and the restore, as the test above: PATCH /me allows five an hour.
 */
test('a rename can be carried into the groups that still use the old name (signed in)', async ({
  page,
}) => {
  const api = await playwrightRequest.newContext({
    baseURL: API_BASE,
    extraHTTPHeaders: { Authorization: `Bearer ${await apiToken()}` },
  });
  const original = ((await (await api.get('/auth/me')).json()) as { name: string }).name;
  const renamed = testMarker('name');
  const following = testMarker('group-following');
  const nicknamed = testMarker('group-nickname');
  const groupIds: number[] = [];
  try {
    // The user's seat takes the account name unless the group is given another.
    for (const data of [
      { name: following, kind: 'trip' },
      { name: nicknamed, kind: 'trip', display_name: `${original} nick` },
    ]) {
      const created = await api.post('/groups', { data });
      expect(created.ok()).toBe(true);
      groupIds.push(((await created.json()) as { id: number }).id);
    }
    const [followingId, nicknamedId] = groupIds;
    const listed = ((await (await api.get('/me/name/groups')).json()) as GroupsUsingName).groups;
    expect(listed.map((group) => group.id)).toContain(followingId);
    expect(listed.map((group) => group.id)).not.toContain(nicknamedId);

    await page.goto(ACCOUNT);
    const input = page.getByTestId('account-name-input');
    await waitForHydration(input);
    const option = page.getByTestId('account-name-groups');
    const checkbox = page.getByRole('checkbox', { name: /Also use this name in my group/ });
    const submit = page.getByTestId('account-name-submit');
    await expect(option).toHaveCount(0);

    // The moment the option mounts (before the browser paints it), the Save button must still be where
    // it was: the option opens from nothing rather than landing a row gap at once and growing from there.
    const before = (await submit.boundingBox())!.y;
    await page.evaluate(() => {
      const record = window as unknown as { __mount?: { top: number; height: number } };
      const observer = new MutationObserver(() => {
        const option = document.querySelector('[data-testid="account-name-groups"]');
        if (!option) return;
        const button = document.querySelector('[data-testid="account-name-submit"]')!;
        record.__mount = {
          top: button.getBoundingClientRect().top,
          height: option.getBoundingClientRect().height,
        };
        observer.disconnect();
      });
      observer.observe(document.body, { childList: true, subtree: true });
    });
    await input.fill(renamed);
    await expect(option).toBeVisible();
    const mount = await page.evaluate(
      () => (window as unknown as { __mount: { top: number; height: number } }).__mount,
    );
    expect(mount.height).toBe(0);
    expect(Math.abs(mount.top - before)).toBeLessThan(0.5);

    const count = listed.length;
    await expect(checkbox).toHaveAccessibleName(
      `Also use this name in my group${count === 1 ? '' : 's'} (${count})`,
    );
    await expect(checkbox).toHaveAccessibleDescription(
      new RegExp(
        `Only groups where you're still called ${escapeRegExp(original)}\\..*${following}`,
      ),
    );
    await expect(page.getByTestId('account-name-groups-list')).not.toContainText(nicknamed);
    await expect(checkbox).not.toBeChecked();
    await settleForScan(page);
    await expectNoA11yViolations(
      page,
      await presetAxeBuilder(page).include('[data-testid="account-name-groups"]').analyze(),
      test.info(),
      'account-name-groups',
      { wholePage: false },
    );

    // Typing the name back hides it again.
    await input.fill(original);
    await expect(option).toHaveCount(0);
    await input.fill(renamed);

    // Keyboard: Tab from the field reaches the box, Space ticks it.
    await input.focus();
    await page.keyboard.press('Tab');
    await expect(checkbox).toBeFocused();
    await page.keyboard.press('Space');
    await expect(checkbox).toBeChecked();

    // Watch the option from here: once it leaves after the save it must not come back.
    await page.evaluate(() => {
      const changes: string[] = [];
      (window as unknown as { __changes: string[] }).__changes = changes;
      let present = !!document.querySelector('[data-testid="account-name-groups"]');
      new MutationObserver(() => {
        const now = !!document.querySelector('[data-testid="account-name-groups"]');
        if (now !== present) changes.push(now ? 'shown' : 'hidden');
        present = now;
      }).observe(document.body, { childList: true, subtree: true });
    });
    await submit.click();
    await expect(
      page.getByText(
        new RegExp(`Your name has been updated, here and in ${listed.length} groups?\\.`),
      ),
    ).toBeVisible();
    await expect(input).toHaveValue(renamed);
    await expect(option).toHaveCount(0);
    await page.waitForTimeout(1000);
    expect(
      await page.evaluate(() => (window as unknown as { __changes: string[] }).__changes),
    ).toEqual(['hidden']);

    const seatName = async (groupId: number) => {
      const group = (await (await api.get(`/groups/${groupId}`)).json()) as {
        members: { is_self: boolean; display_name: string }[];
      };
      return group.members.find((member) => member.is_self)!.display_name;
    };
    expect(await seatName(followingId)).toBe(renamed);
    expect(await seatName(nicknamedId)).toBe(`${original} nick`);

    // The group hub reads the seat live, and its activity says what happened.
    await page.goto(sharedGroup(followingId));
    await expect(
      page.getByText(`${renamed} changed their name in the group to ${renamed}`),
    ).toBeVisible();
    await expect(page.getByRole('row').filter({ hasText: renamed })).toContainText('(you)');
  } finally {
    // The restore brings the seats back too, the same way.
    await api.patch('/me', { data: { name: original, rename_group_seats: true } });
    for (const id of groupIds) await api.delete(`/groups/${id}`);
    await api.dispose();
  }
});
