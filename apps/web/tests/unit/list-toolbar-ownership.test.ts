import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

import { listPages, WEB_ROOT } from '../e2e/helpers/list-pages';

/*
 * One list toolbar, not three.
 *
 * `EntityListToolbar` carries fixes that only work if every list page renders it: the `min-w-48`
 * search item (so the row wraps instead of the search input overflowing onto the filters) and the
 * skipped first debounce run (so a full load past page one is not bounced back to page one). Two
 * pages had hand-rolled copies of the row and kept neither — at 1024px the snapshots scope filter
 * sat UNDER the search input, and `elementFromPoint` at its centre returned the input.
 *
 * So these guards are about ownership, read from source: the pieces a toolbar is made of may appear
 * in exactly one file, and every page that reads a `search` param must reach that file. The first two
 * match the SYNTAX only the thing they mean can produce — an opening JSX tag, a write of the param —
 * because a bare name also matches an import, a comment or a type.
 */

const OWNER = join('components', 'entity-list-toolbar.tsx');

function sources(dir: string): [string, string][] {
  return readdirSync(dir).flatMap((entry): [string, string][] => {
    if (entry === 'node_modules' || entry.startsWith('.') || entry === 'tests') return [];
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return sources(full);
    if (!/\.tsx?$/.test(entry)) return [];
    return [[relative(WEB_ROOT, full), readFileSync(full, 'utf8')]];
  });
}

const SOURCES = ['app', 'components', 'lib'].flatMap((dir) => sources(join(WEB_ROOT, dir)));
const BY_PATH = new Map(SOURCES);

// Files that match `pattern`, other than the owner.
function outsideOwner(pattern: RegExp): string[] {
  return SOURCES.filter(([path, source]) => path !== OWNER && pattern.test(source)).map(
    ([path]) => path,
  );
}

// `@/...` imports only: a toolbar lives in the app, never behind a package or a relative path here.
function resolveImport(specifier: string): string | undefined {
  const base = specifier.slice(2);
  return [`${base}.tsx`, `${base}.ts`, join(base, 'index.tsx'), join(base, 'index.ts')].find(
    (path) => BY_PATH.has(path),
  );
}

// Every app file a page pulls in, transitively — the page's toolbar can sit any number of hops away.
function importClosure(entry: string): Set<string> {
  const seen = new Set<string>();
  const queue = [entry];
  while (queue.length > 0) {
    const path = queue.pop()!;
    if (seen.has(path)) continue;
    seen.add(path);
    const source = BY_PATH.get(path) ?? '';
    for (const match of source.matchAll(/from\s+'(@\/[^']+)'/g)) {
      const resolved = resolveImport(match[1] ?? '');
      if (resolved) queue.push(resolved);
    }
  }
  return seen;
}

const RENDERS_TOOLBAR = /<EntityListToolbar\b/;
const PAGES = listPages();

describe('the list toolbar has one owner', () => {
  it('reads enough source to mean something', () => {
    // A guard on the guards: an empty walk would pass every assertion below.
    expect(SOURCES.length).toBeGreaterThan(200);
    expect(existsSync(join(WEB_ROOT, OWNER))).toBe(true);
    expect(PAGES.length).toBeGreaterThanOrEqual(10);
  });

  it('renders the search input only inside EntityListToolbar', () => {
    expect(RENDERS_TOOLBAR.test(BY_PATH.get(OWNER) ?? '')).toBe(false);
    expect(/<SearchInput\b/.test(BY_PATH.get(OWNER) ?? '')).toBe(true);
    expect(outsideOwner(/<SearchInput\b/)).toEqual([]);
  });

  it('writes the search URL param only from EntityListToolbar', () => {
    /*
     * The other half of a hand-rolled toolbar: a debounced search could sit on a plain `<Input>` and
     * dodge the tag check above, but it still has to WRITE the param — through `navigate({ search })`
     * or a `URLSearchParams.set('search', …)`. Client files only: the server-side fetchers in
     * `lib/api/` set `search` too, on the query string they send the API, which is not the page URL.
     *
     * `search` in KEY position only — right after the `{` or a `,` — so `navigate({ q: search })`,
     * which writes a different param from a variable of that name, does not count as a write.
     */
    const writes = /navigate\(\s*\{(?:[^}]*,)?\s*search\s*[,:}]|\.set\(\s*['"]search['"]/;
    const clientWrites = new RegExp(`^'use client';[\\s\\S]*(?:${writes.source})`);
    expect(clientWrites.test(BY_PATH.get(OWNER) ?? '')).toBe(true);
    expect(outsideOwner(clientWrites)).toEqual([]);
  });

  it('reaches EntityListToolbar from every page that reads a search param', () => {
    const missing = PAGES.filter(
      ({ file }) =>
        ![...importClosure(file)].some((path) => RENDERS_TOOLBAR.test(BY_PATH.get(path) ?? '')),
    ).map(({ file }) => file);
    expect(missing).toEqual([]);
  });

  it('renders EntityListToolbar only on a page that reads the search param it writes', () => {
    // The converse: a toolbar on a page that ignores `search` is a search box that filters nothing.
    const reached = new Set(PAGES.flatMap(({ file }) => [...importClosure(file)]));
    const orphans = SOURCES.filter(
      ([path, source]) => RENDERS_TOOLBAR.test(source) && !reached.has(path),
    ).map(([path]) => path);
    expect(orphans).toEqual([]);
  });

  it('derives the list pages from the pages themselves', () => {
    // Printed shape, so a derivation that collapsed to nothing or to the wrong URLs is visible here.
    const routes = PAGES.map(({ route }) => route);
    expect(routes).toContain('/snapshots');
    expect(routes).toContain('/collections');
    expect(routes.every((route) => /^\/[a-z-]+$/.test(route))).toBe(true);
    expect(dirname(PAGES[0]?.file ?? '')).toMatch(/^app\//);
  });
});
