import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

import { API_BASE, apiToken } from './helpers/api';
import { testMarker } from './helpers/factories';
import { listPages } from './helpers/list-pages';

/*
 * Every list toolbar's controls are reachable: at each width, a click at the centre of every visible
 * control lands on THAT control, and no two controls' boxes overlap or spill out of the toolbar.
 *
 * The failure this exists for was invisible to every other check. A hand-rolled toolbar kept a
 * `min-w-0` search item after `EntityListToolbar` had moved to `min-w-48`, so the flex item shrank
 * while the 192px input inside it did not — it overflowed rightwards and painted over the first
 * filter. At 1024px `elementFromPoint` at the centre of the snapshots scope pills returned the search
 * INPUT: the pills rendered, looked fine in a screenshot, and could not be clicked. The same row cut
 * 9.3px into /collections' add button at 390px.
 *
 * The pages are DERIVED (every page that reads a `search` param, see `helpers/list-pages.ts`), and
 * each must render exactly one `EntityListToolbar` — so a new list page is swept without anybody
 * adding it here, and a page whose toolbar is not the shared one fails by name. Both locales run
 * because Spanish labels are 20-30% longer, which is where a row that fits in English stops fitting.
 */

const WIDTHS = [390, 1024, 1280] as const;
const LOCALES = ['en', 'es'] as const;
const PAGES = listPages();

interface Fixture {
  token: string;
  collectionId: number;
  groupId: number;
}

/*
 * The fullest toolbar the app has, whatever account runs this: /snapshots shows its scope filter only
 * to a member of some group and its collections filter only when a collection exists. Without both,
 * it renders two filters instead of four and cannot reproduce the overflow at all — so the spec makes
 * its own, marked, and deletes them afterwards.
 */
async function seed(request: APIRequestContext): Promise<Fixture> {
  const token = await apiToken();
  const headers = { Authorization: `Bearer ${token}` };
  const marker = testMarker('toolbar');
  const collection = await request.post(`${API_BASE}/collections`, {
    headers,
    data: { name: marker },
  });
  expect(collection.ok(), `creating the collection failed with ${collection.status()}`).toBe(true);
  const group = await request.post(`${API_BASE}/groups`, {
    headers,
    data: { name: marker, kind: 'other' },
  });
  expect(group.ok(), `creating the group failed with ${group.status()}`).toBe(true);
  return { token, collectionId: (await collection.json()).id, groupId: (await group.json()).id };
}

// Never throws: a cleanup raising from `afterAll` would replace the failure that actually happened.
async function unseed(request: APIRequestContext, fixture: Fixture | undefined) {
  if (!fixture) return;
  const headers = { Authorization: `Bearer ${fixture.token}` };
  for (const path of [`/groups/${fixture.groupId}`, `/collections/${fixture.collectionId}`]) {
    const outcome = await request
      .delete(`${API_BASE}${path}`, { headers })
      .then((response) => (response.ok() ? null : `HTTP ${response.status()}`))
      .catch((error: Error) => error.message);
    if (outcome) console.warn(`e2e cleanup: DELETE ${path} did not succeed (${outcome})`);
  }
}

interface ToolbarReport {
  controls: string[];
  groups: number;
  problems: string[];
}

/*
 * Measures the toolbar in the page. "Control" is every visible, pointer-reachable input, button, link
 * or combobox that is not itself inside another one; the search field's clear button is excluded
 * while the field is empty because it is then `pointer-events: none` by design.
 */
function measure(root: Element): ToolbarReport {
  const candidates = [...root.querySelectorAll('input, button, a[href], [role="combobox"]')].filter(
    (el) => {
      const box = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return (
        box.width > 0 &&
        box.height > 0 &&
        style.pointerEvents !== 'none' &&
        style.visibility !== 'hidden'
      );
    },
  );
  const controls = candidates.filter((el) => !candidates.some((o) => o !== el && o.contains(el)));
  const name = (el: Element) =>
    (
      el.getAttribute('aria-label') ||
      el.getAttribute('placeholder') ||
      el.textContent ||
      el.tagName
    )
      .trim()
      .slice(0, 40);
  const problems: string[] = [];
  const bounds = root.getBoundingClientRect();

  for (const el of controls) {
    const box = el.getBoundingClientRect();
    const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    if (!hit || !el.contains(hit)) {
      problems.push(
        `"${name(el)}" is covered by ${hit ? `<${hit.tagName}> "${name(hit)}"` : 'nothing'}`,
      );
    }
    if (box.left < bounds.left - 0.5 || box.right > bounds.right + 0.5) {
      problems.push(`"${name(el)}" spills out of the toolbar`);
    }
  }
  for (let i = 0; i < controls.length; i++) {
    for (let j = i + 1; j < controls.length; j++) {
      const a = controls[i]!.getBoundingClientRect();
      const b = controls[j]!.getBoundingClientRect();
      const width = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const height = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (width > 0.5 && height > 0.5) {
        problems.push(
          `"${name(controls[i]!)}" and "${name(controls[j]!)}" overlap by ${width.toFixed(1)}px`,
        );
      }
    }
  }
  return {
    controls: controls.map(name),
    groups: root.querySelectorAll('[role="group"]').length,
    problems,
  };
}

/*
 * The toolbar's boxes, once they stop moving: every group in it is a `motion` layout item, and a
 * measurement taken mid-animation would report positions the row never settles at.
 *
 * Positions are RELATIVE to the toolbar, so a hint appearing above it — which moves the whole row
 * without changing the row — is not movement. The budget is generous because two of sixty cases
 * once needed more than 10s on a machine at load ~30; a row that is never still still fails.
 */
async function settledReport(page: Page): Promise<ToolbarReport> {
  const toolbar = page.getByTestId('entity-list-toolbar');
  let previous = '';
  await expect(async () => {
    const current = await toolbar.evaluate((root) => {
      const origin = root.getBoundingClientRect();
      return [...root.querySelectorAll('*')]
        .map((el) => {
          const box = el.getBoundingClientRect();
          return `${box.left - origin.left},${box.top - origin.top},${box.width},${box.height}`;
        })
        .join('|');
    });
    const stable = current === previous;
    previous = current;
    expect(stable).toBe(true);
  }).toPass({ intervals: [150], timeout: 30_000 });
  return toolbar.evaluate(measure);
}

test.describe('list toolbars (signed in)', () => {
  let fixture: Fixture | undefined;

  test.beforeAll(async ({ request }) => {
    fixture = await seed(request);
  });

  test.afterAll(async ({ request }) => {
    await unseed(request, fixture);
  });

  test('derives the list pages', () => {
    expect(PAGES.map(({ route }) => route)).toContain('/snapshots');
    expect(PAGES.length).toBeGreaterThanOrEqual(10);
  });

  for (const { route } of PAGES) {
    for (const locale of LOCALES) {
      for (const width of WIDTHS) {
        test(`${route} toolbar controls are reachable at ${width}px in ${locale}`, async ({
          page,
        }) => {
          /*
           * A dev server renders a list route in ~2s warm, but a cold compile (or a loaded machine)
           * has been measured past 40s — longer than the default navigation budget. Patience, not
           * tolerance: the assertions below are unchanged by it.
           */
          test.setTimeout(120_000);
          await page
            .context()
            .addCookies([{ name: 'NEXT_LOCALE', value: locale, domain: 'localhost', path: '/' }]);
          // Tall enough that the whole toolbar sits inside the viewport, where `elementFromPoint` works.
          await page.setViewportSize({ width, height: 1000 });
          // `domcontentloaded`, not `load`: the toolbar and the fonts are awaited explicitly below, and
          // a dev server's first `load` of a route (every chunk and image) has been measured past 90s.
          await page.goto(route, { timeout: 90_000, waitUntil: 'domcontentloaded' });

          // Exactly one, and the shared one: a hand-rolled toolbar carries no such testid.
          await expect(page.getByTestId('entity-list-toolbar')).toHaveCount(1, { timeout: 20_000 });
          await page.evaluate(() => document.fonts.ready);
          const report = await settledReport(page);
          if (route === '/snapshots') {
            /*
             * The fixture's premise, checked rather than assumed: both segmented filters (scope and
             * interval) and the collections filter present, i.e. the four-filter row that overflowed.
             */
            expect(report.groups, '/snapshots lost a segmented filter').toBe(2);
            expect(report.controls.length, '/snapshots lost a filter').toBeGreaterThanOrEqual(9);
          }
          expect(report.problems).toEqual([]);
        });
      }
    }
  }
});
