import { request as playwrightRequest, type APIRequestContext } from '@playwright/test';

import {
  A11Y_LOCALES,
  ADMIN_ROUTES,
  DYNAMIC_ROUTES,
  IN_APP_NOT_FOUND_ROUTE,
  SIGNED_IN_ROUTES,
  UNKNOWN_ROUTE,
  type A11ySeedIds,
} from './helpers/a11y-routes';
import { API_BASE, apiToken } from './helpers/api';
import { ADMIN_AUTH_STATE_PATH, e2eAdminCredentials } from './helpers/auth';
import {
  expect,
  expectNoA11yViolations,
  openForScan,
  presetAxeBuilder,
  scanName,
  test,
} from './helpers/axe';
import { testMarker } from './helpers/factories';

/*
 * Every page a signed-in reader can open, scanned by axe in both languages: each protected route, the
 * public pages (whose header changes once signed in), the invite landing with a LIVE invite (signed in,
 * and signed out in a fresh context), both not-found renders (an unmatched URL, and a `notFound()`
 * inside the app shell), and the dynamic routes — an account's ledger, a group's hub and share flow, a
 * pot and its three flows. Zero tolerance; see `helpers/axe.ts`. The list is derived
 * (`helpers/a11y-routes.ts`, checked by `tests/unit/a11y-sweep-coverage.test.ts`), and `openForScan`
 * fails any target that renders the not-found page or an error boundary instead of itself.
 *
 * The dynamic routes need a state in which each one renders, so the spec seeds it through the API. The
 * pot flows are the demanding part: buy-out, contribute and take-out all `notFound()` unless the pot
 * has a unit price (a holding worth something AND an agreed division), and buy-out also needs a second
 * active seat. So the seed is: a private account (the ledger, and something to contribute); a group
 * with a second, name-only member; a pot holding a second account; an opening division between the
 * two seats; and a link-only invite on the second seat (the live `/join` preview). Everything is named
 * with a per-run marker starting `e2e-a11y-` and removed afterwards, in the order the API allows — the
 * division, then the holding, then the pot, the group and the accounts. A run killed before its cleanup
 * leaves rows under that prefix, which the next run removes first by the same route. Desktop width: the
 * layout that changes on a phone is scanned by `a11y-overlays.auth.spec.ts`.
 *
 * The admin pages render only for an admin, so they are scanned with a second session — the admin
 * account globalSetup signs in from E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD. Without those (a local run
 * with no admin account) those scans skip; CI seeds the account and refuses skips.
 */

const MARKER_PREFIX = 'e2e-a11y-';

interface Seed extends A11ySeedIds {
  inviteToken: string;
  cleanup: () => Promise<void>;
}

// A list endpoint's rows, whether it answers with a bare array or a page.
function rows(body: unknown): { id: number; name?: string; group_id?: number }[] {
  return Array.isArray(body) ? body : ((body as { items?: [] })?.items ?? []);
}

// Empties one pot and deletes it: its division first (a divided pot's holdings cannot leave), then its
// holdings, then the pot. Returns what went wrong, or null.
async function removePot(api: APIRequestContext, potId: number): Promise<string | null> {
  const events = await api.get(`/pots/${potId}/ownership?page_size=100`);
  if (!events.ok()) return `GET ownership: ${events.status()}`;
  const opening = rows(await events.json()).find(
    (row) => (row as { type?: string }).type === 'opening',
  );
  if (opening) {
    // Deleting any opening row takes the whole baseline with it.
    const deleted = await api.delete(`/pots/${potId}/ownership/${opening.id}`);
    if (!deleted.ok()) return `DELETE baseline: ${deleted.status()}`;
  }
  const holdings = await api.get(`/pots/${potId}/holdings`);
  if (!holdings.ok()) return `GET holdings: ${holdings.status()}`;
  const held = (await holdings.json()) as {
    accounts?: { id: number }[];
    investments?: { id: number }[];
  };
  const accountIds = (held.accounts ?? []).map((row) => row.id);
  const investmentIds = (held.investments ?? []).map((row) => row.id);
  if (accountIds.length > 0 || investmentIds.length > 0) {
    const removed = await api.post(`/pots/${potId}/holdings/remove`, {
      data: { account_ids: accountIds, investment_ids: investmentIds },
    });
    if (!removed.ok()) return `remove holdings: ${removed.status()} ${await removed.text()}`;
  }
  const deleted = await api.delete(`/pots/${potId}`);
  return deleted.ok() ? null : `DELETE pot: ${deleted.status()}`;
}

// Removes what a killed run left behind: each marked group's pots, then the group, then the accounts.
async function removeLeftovers(api: APIRequestContext) {
  const groups = await api.get('/groups');
  expect(groups.ok(), `GET /groups: ${groups.status()}`).toBe(true);
  const stale = rows(await groups.json()).filter((row) => row.name?.startsWith(MARKER_PREFIX));
  if (stale.length > 0) {
    const pots = await api.get('/pots');
    expect(pots.ok(), `GET /pots: ${pots.status()}`).toBe(true);
    const allPots = rows(await pots.json());
    for (const group of stale) {
      for (const pot of allPots.filter((row) => row.group_id === group.id)) {
        const problem = await removePot(api, pot.id);
        expect(problem, `removing leftover pot ${pot.id}`).toBeNull();
      }
      const deleted = await api.delete(`/groups/${group.id}`);
      expect(deleted.ok(), `DELETE /groups/${group.id}: ${deleted.status()}`).toBe(true);
    }
  }
  const accounts = await api.get('/accounts?show_archived=true&scope=private&page_size=100');
  expect(accounts.ok(), `GET /accounts: ${accounts.status()}`).toBe(true);
  for (const row of rows(await accounts.json()).filter((r) => r.name?.startsWith(MARKER_PREFIX))) {
    const deleted = await api.delete(`/accounts/${row.id}`);
    expect(deleted.ok(), `DELETE /accounts/${row.id}: ${deleted.status()}`).toBe(true);
  }
}

async function seed(): Promise<Seed> {
  const token = await apiToken();
  const api = await playwrightRequest.newContext({
    baseURL: API_BASE,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  const marker = testMarker('a11y');
  const accounts: number[] = [];
  let groupId: number | null = null;
  let potId: number | null = null;

  async function post<T = { id: number }>(path: string, data: Record<string, unknown>): Promise<T> {
    const response = await api.post(path, { data });
    expect(response.ok(), `POST ${path}: ${response.status()} ${await response.text()}`).toBe(true);
    return (await response.json()) as T;
  }

  // Never throws: a cleanup raising from `afterAll` would replace the failure that actually happened.
  async function cleanup() {
    const problems: string[] = [];
    if (potId !== null) {
      const problem = await removePot(api, potId).catch((error: Error) => error.message);
      if (problem) problems.push(`pot ${potId}: ${problem}`);
    }
    const paths = [
      ...(groupId !== null ? [`/groups/${groupId}`] : []),
      ...accounts.map((id) => `/accounts/${id}`),
    ];
    for (const path of paths) {
      const outcome = await api
        .delete(path)
        .then((response) => (response.ok() ? null : `HTTP ${response.status()}`))
        .catch((error: Error) => error.message);
      if (outcome) problems.push(`DELETE ${path}: ${outcome}`);
    }
    if (problems.length > 0) console.warn(`e2e cleanup did not finish: ${problems.join('; ')}`);
    await api.dispose();
  }

  try {
    await removeLeftovers(api);
    const settings = await (await api.get('/settings')).json();
    const currency: string = settings.primary_currency ?? 'ARS';
    const today = new Date().toISOString().slice(0, 10);
    const account = (name: string) =>
      post('/accounts', {
        name,
        type: 'bank',
        currency,
        opening_balance: '1000.00',
        opening_date: today,
      });

    // Private: the ledger route, and what the contribute flow offers to put in.
    const accountId = (await account(marker)).id;
    accounts.push(accountId);
    // The pot's holding, which is what gives it a value to price units against.
    const potAccountId = (await account(`${marker}-pot`)).id;
    accounts.push(potAccountId);

    groupId = (await post('/groups', { name: marker, kind: 'other' })).id;
    const group = await post<{ members: { id: number; is_self: boolean }[] }>(
      `/groups/${groupId}/members`,
      { display_name: `${marker}-member` },
    );
    const selfId = group.members.find((member) => member.is_self)?.id;
    const otherId = group.members.find((member) => !member.is_self)?.id;
    expect(selfId !== undefined && otherId !== undefined, 'the group has two seats').toBe(true);

    potId = (await post('/pots', { group_id: groupId, base_currency: currency })).id;
    await post(`/pots/${potId}/holdings`, { account_ids: [potAccountId], investment_ids: [] });
    await post(`/pots/${potId}/ownership/opening`, {
      date: today,
      value: '1000.00',
      shares: { [selfId as number]: '60', [otherId as number]: '40' },
    });

    const invite = await post<{ invite_url: string }>(
      `/groups/${groupId}/members/${otherId}/invite`,
      {},
    );
    const inviteToken = new URL(invite.invite_url).searchParams.get('token') ?? '';
    expect(inviteToken, 'the invite link carries a token').not.toBe('');

    return { accountId, groupId, potId, inviteToken, cleanup };
  } catch (error) {
    await cleanup();
    throw error;
  }
}

let ids: Seed;

test.beforeAll(async () => {
  ids = await seed();
});

test.afterAll(async () => {
  await ids?.cleanup();
});

// The invite landing with a live token: the preview a recipient actually sees.
const joinWithInvite = () => `/join?token=${encodeURIComponent(ids.inviteToken)}`;

test.describe('accessibility sweep (signed in)', { tag: '@a11y' }, () => {
  const targets: [string, () => string, boolean][] = [
    ...SIGNED_IN_ROUTES.map((route): [string, () => string, boolean] => [
      route,
      () => route,
      false,
    ]),
    [UNKNOWN_ROUTE, () => UNKNOWN_ROUTE, true],
    [IN_APP_NOT_FOUND_ROUTE, () => IN_APP_NOT_FOUND_ROUTE, true],
    ['/join (live invite)', joinWithInvite, false],
    ...Object.entries(DYNAMIC_ROUTES).map(([pattern, url]): [string, () => string, boolean] => [
      pattern,
      () => url(ids),
      false,
    ]),
  ];

  for (const locale of A11Y_LOCALES) {
    for (const [route, url, notFound] of targets) {
      test(`${route} has no axe violations (${locale})`, async ({ page, makeAxeBuilder }, info) => {
        await openForScan(page, url(), locale, { notFound });
        const results = await makeAxeBuilder().analyze();
        await expectNoA11yViolations(page, results, info, scanName(route, locale), {
          wholePage: true,
        });
      });
    }

    /*
     * The same live invite as a recipient with no session sees it — the common case, since most open
     * the link signed out. A fresh context rather than the signed-out spec, because only this spec has
     * the token: minting one needs the group admin's session.
     */
    test(`/join (live invite, signed out) has no axe violations (${locale})`, async ({
      browser,
    }, info) => {
      const context = await browser.newContext({ storageState: { cookies: [], origins: [] } });
      try {
        const page = await context.newPage();
        await openForScan(page, joinWithInvite(), locale);
        const results = await presetAxeBuilder(page).analyze();
        await expectNoA11yViolations(page, results, info, scanName('join-signed-out', locale), {
          wholePage: true,
        });
      } finally {
        await context.close();
      }
    });
  }
});

/*
 * What each admin page shows only when it rendered its content, not just its frame: the invite form,
 * and the feedback table (CI seeds feedback, so the table and its category badges are in the scan
 * rather than the empty state). `openForScan` already refuses the not-found page a non-admin gets.
 */
const ADMIN_PREMISES: Record<string, string> = {
  '/admin': '[data-testid="admin-invite-email"]',
  '/admin/feedback': 'table',
};

test.describe('accessibility sweep (admin)', { tag: '@a11y' }, () => {
  test.skip(
    e2eAdminCredentials() === null,
    'E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD are unset (CI seeds an admin account)',
  );
  test.use({ storageState: ADMIN_AUTH_STATE_PATH });

  for (const locale of A11Y_LOCALES) {
    for (const route of ADMIN_ROUTES) {
      test(`${route} has no axe violations (${locale}, admin)`, async ({
        page,
        makeAxeBuilder,
      }, info) => {
        await openForScan(page, route, locale);
        const premise = ADMIN_PREMISES[route];
        expect(premise, `${route} has no premise in ADMIN_PREMISES`).toBeDefined();
        await expect(page.locator(premise as string).first()).toBeVisible();
        const results = await makeAxeBuilder().analyze();
        await expectNoA11yViolations(page, results, info, scanName(`${route}-admin`, locale), {
          wholePage: true,
        });
      });
    }
  }
});
