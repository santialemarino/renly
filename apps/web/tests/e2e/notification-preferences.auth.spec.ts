import { expect, test, type Page } from '@playwright/test';

import { ROUTES } from '@/config/routes';
import { NOTIFICATION_EVENTS } from '@/lib/constants/notifications';

/*
 * The preferences surface, which is where both halves of this unit become visible to a person.
 *
 * Two things are worth a browser and could not be covered anywhere else.
 *
 * The GRID is built by mapping the web's own `NOTIFICATION_EVENTS`, while the rows it can ever be
 * filled by come from the API's `NotificationEvent` — two transcriptions of one list in two languages.
 * `apps/api/tests/unit/test_notification_event_surface.py` asserts they agree as sets; this asserts the
 * agreement actually reaches a rendered page, with real preference rows fetched from a real API. A row
 * present in the constant and absent from the enum renders here as a switch for an event that can never
 * fire, which no static comparison can see.
 *
 * The CADENCE switch cannot be unit-tested at all: it is a Radix primitive, and `apps/web` and
 * `packages/ui` declare different React ranges, so a jsdom render dies inside the primitive with
 * `Cannot read properties of null (reading 'useState')`. The `testing` skill records that; the
 * consequence is that a browser is the only place its round trip exists.
 *
 * NOT covered, stated rather than implied: a digest actually arriving. It is sent by an hourly
 * scheduler job at the reader's own local evening hour, so no spec can wait for one — the job's own
 * behaviour is pinned in `tests/unit/test_notification_digest_service.py` and its three SQL statements
 * in `tests/integration/test_notification_queries.py`.
 */

// The two events this unit added. Named as literals rather than derived, so the test states what it is
// about — deriving them from the same constant the page maps would make it agree with itself.
const NEW_EVENTS = ['obligation_due', 'plan_charged'] as const;

// next-intl answers a missing message by returning its own key path, so an unlabelled row renders the
// string `notifications.events.plan_charged.label` rather than nothing at all. Asserting "not empty"
// would pass on exactly that.
function expectRealCopy(text: string | null, key: string) {
  expect(text, `${key} rendered nothing`).toBeTruthy();
  expect(text, `${key} rendered its own key path`).not.toContain(key);
}

async function openPreferences(page: Page) {
  await page.goto(ROUTES.notifications);
  await expect(page.getByTestId('notification-digest-switch')).toBeVisible();
}

test.describe('notification preferences', () => {
  test('the grid renders a labelled row for every event the app knows about', async ({ page }) => {
    await openPreferences(page);

    for (const event of NOTIFICATION_EVENTS) {
      const row = page.getByTestId(`notification-event-${event}`);
      await expect(row, `no grid row for ${event}`).toBeVisible();
      expectRealCopy(await row.locator('th').textContent(), event);
      // Three switches, one per channel. A row that renders its label and no controls is a row nobody
      // can act on, which reads as present while being useless.
      await expect(row.getByRole('switch')).toHaveCount(3);
    }
  });

  test('the two new events are among them', async ({ page }) => {
    // The specific claim, separate from the general one above: the sweep would still pass if the two
    // new events had been left out of BOTH the constant and the enum, because it iterates the constant.
    await openPreferences(page);
    for (const event of NEW_EVENTS) {
      await expect(page.getByTestId(`notification-event-${event}`)).toBeVisible();
    }
  });

  test('the email cadence round-trips through a reload', async ({ page }) => {
    // One test, not two: splitting the flip and the check would make the second depend on the first
    // having run, which `workers: 1` happens to guarantee today and no spec should rely on.
    //
    // It also runs against a REAL account whose cadence is whatever it already was, so it reads that
    // first and restores it in a `finally` — the harness must leave no trace, the same rule the
    // expense factory follows with its marker.
    await openPreferences(page);
    const digest = page.getByTestId('notification-digest-switch');
    const original = await digest.getAttribute('data-state');

    try {
      await digest.click();
      const flipped = original === 'checked' ? 'unchecked' : 'checked';
      await expect(digest).toHaveAttribute('data-state', flipped);

      // The reload is the point. The switch reflecting a click proves only that React re-rendered;
      // this proves the answer reached the API, was stored, and came back on the next server render.
      await page.reload();
      await expect(page.getByTestId('notification-digest-switch')).toHaveAttribute(
        'data-state',
        flipped,
      );
    } finally {
      const control = page.getByTestId('notification-digest-switch');
      if ((await control.getAttribute('data-state')) !== original) {
        await control.click();
        await expect(control).toHaveAttribute('data-state', original!);
      }
    }
  });
});
