import { request as playwrightRequest, type APIRequestContext } from '@playwright/test';

import {
  A11Y_LOCALES,
  DYNAMIC_ROUTES,
  SIGNED_IN_ROUTES,
  UNKNOWN_ROUTE,
  type A11ySeedIds,
} from './helpers/a11y-routes';
import { API_BASE, apiToken } from './helpers/api';
import { expect, expectNoA11yViolations, openForScan, scanName, test } from './helpers/axe';
import { testMarker } from './helpers/factories';

/*
 * Every page a signed-in reader can open, scanned by axe in both languages: each protected route, the
 * public pages (whose header changes once signed in), the invite landing, the not-found page, and the
 * dynamic routes — an account's ledger, a group's hub and share flow, a pot and its three flows. Zero
 * tolerance; see `helpers/axe.ts`. The list is derived (`helpers/a11y-routes.ts`, checked by
 * `tests/unit/a11y-sweep-coverage.test.ts`).
 *
 * The dynamic routes need something to show, so the spec seeds it through the API: an account, a group
 * with a second, name-only member (so the hub's roster and a pot's flows have another person in them),
 * and a pot. Everything is named with a per-run marker starting `e2e-a11y-` and deleted afterwards; a
 * run that was killed before its cleanup leaves rows under that prefix, which the next run deletes
 * first. Desktop width: the layout that changes on a phone (the nav bar and its sheet) is scanned by
 * `a11y-overlays.auth.spec.ts`.
 */

const MARKER_PREFIX = 'e2e-a11y-';

interface Seed extends A11ySeedIds {
  cleanup: () => Promise<void>;
}

// A list endpoint's rows, whether it answers with a bare array or a page.
function rows(body: unknown): { id: number; name?: string }[] {
  return Array.isArray(body) ? body : ((body as { items?: [] })?.items ?? []);
}

// Deletes what a killed run left behind: groups first (a group takes its pots with it), then accounts.
async function removeLeftovers(api: APIRequestContext) {
  for (const path of ['/groups', '/accounts?show_archived=true&scope=private&page_size=100']) {
    const listed = await api.get(path);
    expect(listed.ok(), `GET ${path}: ${listed.status()}`).toBe(true);
    const base = path.split('?')[0];
    for (const row of rows(await listed.json()).filter((r) => r.name?.startsWith(MARKER_PREFIX))) {
      const deleted = await api.delete(`${base}/${row.id}`);
      expect(deleted.ok(), `DELETE ${base}/${row.id}: ${deleted.status()}`).toBe(true);
    }
  }
}

async function seed(): Promise<Seed> {
  const token = await apiToken();
  const api = await playwrightRequest.newContext({
    baseURL: API_BASE,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  const marker = testMarker('a11y');
  const created: string[] = [];

  async function post(path: string, data: Record<string, unknown>): Promise<number> {
    const response = await api.post(path, { data });
    expect(response.ok(), `POST ${path}: ${response.status()} ${await response.text()}`).toBe(true);
    return (await response.json()).id as number;
  }

  // Never throws: a cleanup raising from `afterAll` would replace the failure that actually happened.
  async function cleanup() {
    for (const path of created.reverse()) {
      const outcome = await api
        .delete(path)
        .then((response) => (response.ok() ? null : `HTTP ${response.status()}`))
        .catch((error: Error) => error.message);
      if (outcome) console.warn(`e2e cleanup: DELETE ${path} did not succeed (${outcome})`);
    }
    await api.dispose();
  }

  try {
    await removeLeftovers(api);
    const settings = await (await api.get('/settings')).json();
    const currency: string = settings.primary_currency ?? 'ARS';
    const today = new Date().toISOString().slice(0, 10);

    const accountId = await post('/accounts', {
      name: marker,
      type: 'bank',
      currency,
      opening_balance: '1000.00',
      opening_date: today,
    });
    created.push(`/accounts/${accountId}`);
    const groupId = await post('/groups', { name: marker, kind: 'other' });
    created.push(`/groups/${groupId}`);
    await post(`/groups/${groupId}/members`, { display_name: `${marker}-member` });
    const potId = await post('/pots', { group_id: groupId, base_currency: currency });
    created.push(`/pots/${potId}`);
    return { accountId, groupId, potId, cleanup };
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

test.describe('accessibility sweep (signed in)', { tag: '@a11y' }, () => {
  const targets: [string, () => string][] = [
    ...[...SIGNED_IN_ROUTES, UNKNOWN_ROUTE].map((route): [string, () => string] => [
      route,
      () => route,
    ]),
    ...Object.entries(DYNAMIC_ROUTES).map(([pattern, url]): [string, () => string] => [
      pattern,
      () => url(ids),
    ]),
  ];

  for (const locale of A11Y_LOCALES) {
    for (const [route, url] of targets) {
      test(`${route} has no axe violations (${locale})`, async ({ page, makeAxeBuilder }, info) => {
        await openForScan(page, url(), locale);
        const results = await makeAxeBuilder().analyze();
        await expectNoA11yViolations(page, results, info, scanName(route, locale), {
          wholePage: true,
        });
      });
    }
  }
});
