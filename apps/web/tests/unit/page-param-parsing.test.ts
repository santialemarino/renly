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
      .filter(
        ([, source]) => /\bpage\??:\s*string/.test(source) && !source.includes('resolvePageParam'),
      )
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });

  it('the scan actually finds pages', () => {
    // The guard on the guard: both assertions above are filters that pass trivially over an empty
    // list, so a broken walk (a moved app/ directory, a renamed page file) would read as every page
    // being clean rather than as no page being checked.
    expect(pages().length).toBeGreaterThan(20);
  });
});
