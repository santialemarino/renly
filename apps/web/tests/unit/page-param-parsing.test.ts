import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/*
 * A structural guard over how a `?page=` value reaches the API (SEC-11).
 *
 * The rule is one line — parse it with `resolvePageParam` — and the reason it needs a guard rather
 * than a convention is what happened without one: five pages each rolled their own, and the three
 * answers they arrived at were not equivalent. `/notifications` clamped properly, the account ledger
 * clamped `NaN` but forwarded a fractional page, and `/expenses`, `/income` and `/investments` did
 * `params.page ? Number(params.page) : 1` — which sends the literal string `NaN` for `?page=abc`.
 *
 * What makes that worth a test rather than a comment is the failure mode. The API's `ge=1` answers a
 * bad page with a 422, the server component's fetch rejects, and `apps/web` has no `error.tsx` — so a
 * hand-edited query string is Next's generic crash screen rather than page 1. It is invisible in
 * review (every copy looks reasonable), invisible to `tsc` (they all typecheck), and invisible to the
 * suite (nothing rendered a page with a bad param).
 *
 * The check reads SOURCE TEXT and is a scan over every page rather than an assertion per page, which
 * is the property that matters: a list of the five known offenders would have nothing to say about
 * the sixth page somebody writes next week, and that page is the one this exists for.
 */

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, '..', '..', 'app');

// Every `page.tsx` under app/, as [path relative to app/, source].
function pages(): [string, string][] {
  const out: [string, string][] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      if (entry === 'node_modules' || entry.startsWith('.')) continue;
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry === 'page.tsx') out.push([relative(APP, full), readFileSync(full, 'utf8')]);
    }
  };
  walk(APP);
  return out;
}

/*
 * Whether a file turns a page param into a number by hand.
 *
 * Matches `Number(` / `parseInt(` applied to something whose name ends in `page` or `Page`, case
 * insensitively — the shape all three hand-rolled versions took. It deliberately does NOT match
 * `resolvePageParam(query.page)`, which is the call this guard is steering everything towards.
 */
function hasHandRolledParse(source: string): boolean {
  return /\b(?:Number|parseInt)\(\s*(?:\w+\.)?\w*[pP]age\b/.test(source);
}

/*
 * Whether a file declares a page param in its searchParams type, under ANY name.
 *
 * `\w*[pP]age` rather than `\bpage`, and that is the whole point: a word boundary before `page` missed
 * `expensesPage?: string`, `incomePage?: string` and `settlementsPage?: string` — the three namespaced
 * params SEC-11 itself introduced on the group hub. The guard was blind to exactly the shape the same
 * change had just created, and the hub passed only because its source happened to mention the parser
 * for other reasons.
 */
function declaresAPageParam(source: string): boolean {
  return /\b\w*[pP]age\??:\s*string/.test(source);
}

describe('every page parses ?page= the same way', () => {
  it('no page.tsx turns a page param into a number by hand', () => {
    const offenders = pages()
      .filter(([, source]) => hasHandRolledParse(source))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });

  it('every page that reads a page param resolves it through the shared parser', () => {
    // The direction the check above cannot see: a page could read `searchParams.page` and forward the
    // raw STRING, which typechecks (the fetchers take a number, but a template literal does not care)
    // and reaches the API unparsed. Requiring the import wherever a page param is read closes that.
    const offenders = pages()
      .filter(([, source]) => declaresAPageParam(source) && !source.includes('resolvePageParam'))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });

  it('sees a namespaced page param, not only a bare one', () => {
    // The hole this guard shipped with, asserted as a property of the matcher rather than left to a
    // page happening to trip it: three of the params in this very change are prefixed.
    expect(declaresAPageParam('page?: string')).toBe(true);
    expect(declaresAPageParam('expensesPage?: string')).toBe(true);
    expect(declaresAPageParam('incomePage?: string')).toBe(true);
    expect(declaresAPageParam('settlementsPage?: string')).toBe(true);
    expect(declaresAPageParam('kind?: string')).toBe(false);
  });

  it('the scan actually finds pages', () => {
    // The guard on the guard: both assertions above are filters that pass trivially over an empty
    // list, so a broken walk (a moved app/ directory, a renamed page file) would read as every page
    // being clean rather than as no page being checked.
    expect(pages().length).toBeGreaterThan(20);
  });
});

/*
 * The empty state of a paginated surface must be decided by the TOTAL, never by the rows on the page.
 *
 * This is the rule SEC-11 discovered, wrote a test for, and then applied to one of ten surfaces. The
 * two differ exactly on a page past the end — reachable by a hand-typed URL and by deleting the last
 * row of the last page — and answering "this page holds nothing" with "nothing has ever happened
 * here" is both false and a dead end, because the pager renders in the other branch.
 *
 * Matched on the SOURCE of every component that renders a pager, because "which surfaces paginate" is
 * the thing that grows: a list of the known ones would say nothing about the eleventh.
 */
function paginatedComponents(): [string, string][] {
  const out: [string, string][] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      if (entry === 'node_modules' || entry.startsWith('.')) continue;
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry.endsWith('.tsx')) {
        const source = readFileSync(full, 'utf8');
        // Only surfaces whose empty state REPLACES the table. Where it is a `TableEmptyRow` inside
        // the table body the pager still renders below it, so testing the page's own length there is
        // correct — it picks a row, it does not hide the control.
        if (source.includes('<TablePagination') && !source.includes('TableEmptyRow')) {
          out.push([relative(APP, full), source]);
        }
      }
    }
  };
  walk(APP);
  return out;
}

describe('a paginated surface decides its empty state from the total', () => {
  it('no paginated component gates an empty state on the page length', () => {
    // `rows.length === 0 ?` in a component that also renders a pager is the shape that strands the
    // reader. `total === 0 ?` is the same test asked of the right number.
    const offenders = paginatedComponents()
      .filter(([, source]) => /\)?\s*:?\s*\w+\.length === 0 \?/.test(source))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });

  it('the scan finds the paginated components', () => {
    // The guard on the guard: the filter above passes trivially over an empty list, so a renamed
    // pager component would read as every surface being clean.
    expect(paginatedComponents().length).toBeGreaterThanOrEqual(8);
  });
});
