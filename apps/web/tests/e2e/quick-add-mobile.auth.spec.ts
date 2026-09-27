import { expect, test, type Page } from '@playwright/test';

import { API_BASE, apiToken } from './helpers/api';
import { deleteExpenseByMarker, expenseRow, testMarker } from './helpers/factories';

// Route literals mirror apps/web/config/routes.ts, kept local like every spec's. /snapshots rather
// than the dashboard, which auto-starts the welcome tour on an account that has not finished
// onboarding — see mobile-navigation.auth.spec.ts.
const START = '/snapshots';
const EXPENSES = '/expenses';

const PHONE = { width: 390, height: 844 };
const DESKTOP = { width: 1280, height: 900 };

// The nav list inside the sidebar, and the hamburger that opens it as a Sheet below `md`.
const NAV = '[data-testid="sidebar-nav"]';
const HAMBURGER = '[data-sidebar="trigger"]';

// The four entry forms, by the ids their `<form>` elements carry.
const EXPENSE_FORM = 'form#expense-form';
const INCOME_FORM = 'form#income-form';
const SHARED_EXPENSE_FORM = 'form#shared-expense-form';
const SHARED_INCOME_FORM = 'form#shared-income-form';

/*
 * How long a form has to stay up after the sheet is gone before it counts as having survived it.
 *
 * The defect this pins unmounted the form about 300ms after it appeared — the Sheet's close animation
 * (`duration-300`), after which Radix unmounts the Sheet and everything rendered inside it. A second
 * is three times that plus the swap's own 200ms exit, so a form owned by the Sheet cannot last it,
 * and an assertion made the instant the form appears — before the Sheet has finished leaving — would
 * pass on exactly the broken code. This is the one place a fixed wait is the assertion rather than a
 * stand-in for one: the claim is "still there LATER".
 */
const OUTLAST_MS = 1_000;

/*
 * The first open's budget. The quick-add awaits six reads and preloads five chunks before it opens
 * anything, and on a dev server the first open also compiles those chunks — past the 5s `expect`
 * default after a cold start (see createExpenseViaQuickAdd). Patience, not tolerance: the assertion
 * is unchanged, and a production build compiles nothing here.
 */
const QUICK_ADD_OPEN_MS = 20_000;

// The `id` each entry form's `<form>` carries, as it appears in the compiled chunk that ships it — how
// a fetched script is recognised as a form chunk.
const FORM_CHUNK_MARKERS = [
  '"expense-form"',
  '"income-form"',
  '"shared-expense-form"',
  '"shared-income-form"',
];

const TYPE_INCOME = /^(Income|Ingreso)$/;
const TYPE_EXPENSE = /^(Expense|Gasto)$/;

// Every open dialog on the page. The Sheet is one too (Radix renders it as `role="dialog"`), which
// is what lets "exactly one" mean "the form, and the sheet is gone".
function dialogs(page: Page) {
  return page.getByRole('dialog');
}

// Opens the quick-add the way a phone reader has to: the hamburger, then the trigger inside the sheet.
async function openFromSheet(page: Page) {
  await page.locator(HAMBURGER).click();
  await expect(page.locator(NAV)).toBeVisible();
  await page.getByTestId('quick-add-trigger').click();
}

/*
 * The form is the ONLY dialog, is still mounted OUTLAST_MS after the sheet left, and takes input.
 *
 * "Takes input" is asserted by typing into it, because a dialog that is mounted but inert — under a
 * stale overlay, or with `pointer-events` left off the body by a layer that closed around it — would
 * satisfy every visibility check here and still be useless.
 */
async function expectFormSurvives(page: Page, form: string, probe: string) {
  await expect(page.locator(form)).toBeVisible({ timeout: QUICK_ADD_OPEN_MS });
  await expect(page.locator(NAV)).toHaveCount(0);
  await page.waitForTimeout(OUTLAST_MS);

  await expect(dialogs(page)).toHaveCount(1);
  const notes = dialogs(page).locator(`${form} textarea`).first();
  await expect(notes).toBeVisible();
  await notes.fill(probe);
  await expect(notes).toHaveValue(probe);
}

/*
 * Records which form chunks the page fetches, from the moment it is called. Every JS response body is
 * read and checked for a form's id; `seen()` waits for the reads still in flight before answering, so
 * a chunk that arrived just before the question is not missed.
 */
function watchFormChunks(page: Page) {
  const found = new Set<string>();
  const reads: Promise<void>[] = [];
  page.on('response', (response) => {
    if (!new URL(response.url()).pathname.endsWith('.js')) return;
    reads.push(
      response
        .text()
        .then((body) =>
          FORM_CHUNK_MARKERS.filter((m) => body.includes(m)).forEach((m) => found.add(m)),
        )
        .catch(() => undefined),
    );
  });
  return {
    seen: async () => {
      await Promise.all(reads);
      return [...found];
    },
  };
}

// Swaps the open form's entry TYPE through its own toggle — the expense ↔ income swap.
async function swapType(page: Page, type: RegExp) {
  await dialogs(page).getByRole('radio', { name: type }).click();
}

// Swaps the open form's SCOPE through its own picker: a group by name, or "just me" (always first).
async function swapScope(page: Page, groupName: string | null) {
  await dialogs(page).locator('#entry-scope').click();
  const options = page.getByRole('option');
  await (groupName === null ? options.first() : options.filter({ hasText: groupName })).click();
}

/*
 * The quick-add on a phone, which is the one surface its forms were ever lost on.
 *
 * Below `md` the sidebar is a Sheet, the trigger lives in it, and opening a form closes it — a closed
 * Sheet is unmounted, and the forms used to be owned inside it, so each one appeared and was gone a
 * third of a second later. Nothing short of a browser at a phone width can see that: the forms render,
 * type-check and pass every unit test either way. `tests/unit/quick-add-ownership.test.ts` holds the
 * structure that fixes it; this holds the behaviour.
 *
 * A throwaway group is created through the API so the two SHARED forms are reachable too — the scope
 * picker renders only for a group member, and the harness account may belong to none. Deleted in
 * `afterAll`; it never carries an entry, since nothing here submits a shared form.
 */
test.describe('quick-add forms outlive the mobile sheet (signed in)', () => {
  const groupName = testMarker('quick-add-group');
  let groupId: number | null = null;
  // Read once and reused by the teardown, so the cleanup cannot fail on a second read and leak the group.
  let token = '';

  test.beforeAll(async ({ request }) => {
    token = await apiToken();
    const response = await request.post(`${API_BASE}/groups`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { name: groupName, kind: 'other' },
    });
    expect(response.ok(), `creating the test group failed with ${response.status()}`).toBe(true);
    groupId = (await response.json()).id;
  });

  test.afterAll(async ({ request }) => {
    if (groupId === null) return;
    await request.delete(`${API_BASE}/groups/${groupId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });

  test('every entry form opened from the sheet outlasts the sheet, and swaps', async ({ page }) => {
    await page.setViewportSize(PHONE);
    await page.goto(START);

    await openFromSheet(page);
    await expectFormSurvives(page, EXPENSE_FORM, 'probe expense');

    await swapType(page, TYPE_INCOME);
    await expectFormSurvives(page, INCOME_FORM, 'probe income');
    await expect(page.locator(EXPENSE_FORM)).toHaveCount(0);

    await swapScope(page, groupName);
    await expectFormSurvives(page, SHARED_INCOME_FORM, 'probe shared income');

    await swapType(page, TYPE_EXPENSE);
    await expectFormSurvives(page, SHARED_EXPENSE_FORM, 'probe shared expense');

    await swapScope(page, null);
    await expectFormSurvives(page, EXPENSE_FORM, 'probe expense again');

    await page.keyboard.press('Escape');
    await expect(dialogs(page)).toHaveCount(0);
  });

  test('an expense added from the sheet reaches the list', async ({ page }) => {
    const marker = testMarker('quick-add-mobile');

    try {
      await page.setViewportSize(PHONE);
      await page.goto(START);
      await openFromSheet(page);

      /*
       * The survival check comes BEFORE any typing, and that order is the test. On the old shape the
       * form lived about 300ms after appearing — enough for a fast fill and submit to land inside it,
       * so a flow that typed straight away passed on the very bug. Waiting out the sheet first means
       * the save below can only happen in a form that outlived it.
       */
      await expectFormSurvives(page, EXPENSE_FORM, marker);

      await page.getByTestId('expense-form-amount').fill('42.50');
      await page.getByTestId('expense-form-submit').click();
      // The dialog closing is the save's own acknowledgement — the submit handler closes it only after
      // the action resolves.
      await expect(page.getByTestId('expense-form-notes')).toBeHidden();

      await page.goto(EXPENSES);
      await expect(expenseRow(page, marker)).toHaveCount(1);
    } finally {
      await deleteExpenseByMarker(page, marker);
    }
  });

  test('no form chunk downloads before the first open, at either width', async ({ page }) => {
    /*
     * The forms are `next/dynamic` so they stay out of every protected page's bundle — but a dynamic
     * component fetches its chunk as soon as it RENDERS, open or not. Rendered from page load, they
     * downloaded on every protected page at every width; the owner now renders them only after the
     * first open. The second half is the premise: the same watcher does see the chunks once the
     * quick-add is opened, so an empty first answer means "not fetched", not "not recognisable".
     */
    for (const viewport of [PHONE, DESKTOP]) {
      await page.setViewportSize(viewport);
      const chunks = watchFormChunks(page);
      await page.goto(START, { waitUntil: 'networkidle' });
      await page.waitForTimeout(OUTLAST_MS);
      expect(await chunks.seen(), `form chunks fetched at load, width ${viewport.width}`).toEqual(
        [],
      );

      if (viewport === PHONE) await openFromSheet(page);
      else await page.getByTestId('quick-add-trigger').click();
      await expect(page.locator(EXPENSE_FORM)).toBeVisible({ timeout: QUICK_ADD_OPEN_MS });
      expect(await chunks.seen()).toContain('"expense-form"');
      await page.keyboard.press('Escape');
      await expect(dialogs(page)).toHaveCount(0);
    }
  });

  test('at a desktop width, with no sheet, the forms open and swap unchanged', async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await page.goto(START);

    // The permanent sidebar: the trigger is visible without the hamburger, and stays put throughout.
    await expect(page.locator(NAV)).toBeVisible();
    await page.getByTestId('quick-add-trigger').click();
    await expect(page.locator(EXPENSE_FORM)).toBeVisible({ timeout: QUICK_ADD_OPEN_MS });
    await page.waitForTimeout(OUTLAST_MS);
    await expect(dialogs(page)).toHaveCount(1);

    await swapType(page, TYPE_INCOME);
    await expect(page.locator(INCOME_FORM)).toBeVisible();
    await expect(page.locator(EXPENSE_FORM)).toHaveCount(0);
    await expect(dialogs(page)).toHaveCount(1);

    await swapType(page, TYPE_EXPENSE);
    await expect(page.locator(EXPENSE_FORM)).toBeVisible();
    await expect(page.locator(INCOME_FORM)).toHaveCount(0);

    await page.keyboard.press('Escape');
    await expect(dialogs(page)).toHaveCount(0);
    await expect(page.locator(NAV)).toBeVisible();
  });
});
