import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/*
 * Structural guards over the focus system, reading source text across the app and `packages/ui`.
 *
 * Each one pins a CLASS rather than the instances fixed with it, by walking the tree for the shape the
 * defect takes, so a new call site is covered the day it is written. What these cannot see is
 * behaviour — whether a ring actually clears 3:1, whether focus actually comes back — and that lives in
 * the browser, in `tests/e2e/focus-system*.spec.ts`. These catch the regressions a render would only
 * show on the one page somebody happened to open.
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');
const REPO = join(WEB, '..', '..');
const UI = join(REPO, 'packages', 'ui', 'src');

function readSources(root: string, extensions: string[]): [string, string][] {
  const out: [string, string][] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      if (entry === 'node_modules' || entry.startsWith('.')) continue;
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (extensions.some((extension) => entry.endsWith(extension)))
        out.push([relative(REPO, full), readFileSync(full, 'utf8')]);
    }
  };
  walk(root);
  return out;
}

/*
 * Each JSX opening tag matching `start`, up to the `>` that closes it — found by tracking brace depth,
 * because a prop like `onClick={(e) => …}` carries a `>` of its own.
 */
function openingTags(source: string, start: RegExp): string[] {
  return [...source.matchAll(start)].map((match) => {
    let depth = 0;
    for (let index = match.index; index < source.length; index += 1) {
      const char = source[index];
      if (char === '{') depth += 1;
      else if (char === '}') depth -= 1;
      else if (char === '>' && depth === 0) return source.slice(match.index, index + 1);
    }
    return source.slice(match.index);
  });
}

const APP = [
  ...readSources(join(WEB, 'app'), ['.tsx', '.ts', '.css']),
  ...readSources(join(WEB, 'components'), ['.tsx', '.ts']),
  ...readSources(join(WEB, 'lib'), ['.tsx', '.ts']),
];
const STYLED = [...APP, ...readSources(UI, ['.tsx', '.ts', '.css'])];

describe('the neutral focus ring is solid', () => {
  it('finds sources to check', () => {
    // A guard on the guard: an empty walk would pass every assertion below.
    expect(STYLED.length).toBeGreaterThan(150);
    expect(STYLED.some(([path]) => path.endsWith(join('styles', 'index.css')))).toBe(true);
  });

  /*
   * `--ring` is dark enough to clear 3:1 on its own; halving its alpha is what took the old ring to
   * 1.2:1, so both the utility form and the hand-written CSS form are refused. The variant-tinted rings
   * (`ring-red-500/50`, `ring-blue-800/50`) are other tokens and keep their alpha.
   */
  it('never draws the ring token at a reduced alpha', () => {
    const utility = /\b(?:ring|border|outline)-(?:sidebar-)?ring\/[\d[]/g;
    const mixed = /color-mix\([^)]*var\(--(?:sidebar-)?ring\)\s*\d/g;
    const offenders = STYLED.flatMap(([path, source]) =>
      [...source.matchAll(utility), ...source.matchAll(mixed)].map(
        (match) => `${path}: ${match[0]}`,
      ),
    );
    expect(offenders).toEqual([]);
  });

  // The ring token is the FOCUS colour; a hover that borrows it would paint hover as dark as focus.
  it('never uses the ring token as a hover border', () => {
    const offenders = STYLED.flatMap(([path, source]) =>
      [...source.matchAll(/\bhover:border-(?:sidebar-)?ring\b/g)].map(
        (match) => `${path}: ${match[0]}`,
      ),
    );
    expect(offenders).toEqual([]);
  });
});

/*
 * Every Radix Dialog in the codebase is one of the base wrappers, and every wrapper returns focus.
 *
 * Radix returns focus only to its own `Dialog.Trigger`, and the app's dialogs are controlled, so a
 * wrapper that renders `<X.Content>` without `useReturnFocus` drops focus to <body> on every close. The
 * population is derived from the import: any file that pulls in the Radix dialog is a wrapper.
 */
describe('every dialog primitive returns focus to its opener', () => {
  // Both spellings of the Radix dialog: the scoped package and the `radix-ui` umbrella.
  const RADIX_DIALOG = /from '@radix-ui\/react-dialog'|import[^;]*\bDialog\b[^;]*from 'radix-ui'/;
  const wrappers = readSources(UI, ['.tsx']).filter(([, source]) => RADIX_DIALOG.test(source));

  it('finds the wrappers', () => {
    // Dialog and Sheet today. Missing either means the derivation broke, not that they went away.
    expect(wrappers.map(([path]) => path.split(sep).pop())).toEqual(
      expect.arrayContaining(['dialog.tsx', 'sheet.tsx']),
    );
  });

  it('routes each wrapper’s content through useReturnFocus', () => {
    const offenders = wrappers.flatMap(([path, source]) => {
      const contents = openingTags(source, /<\w+\.Content\b/g);
      if (contents.length === 0) return [`${path}: renders no Content`];
      return contents
        .filter(
          (content) =>
            !content.includes('onOpenAutoFocus={returnFocus.onOpenAutoFocus}') ||
            !content.includes('onCloseAutoFocus={returnFocus.onCloseAutoFocus}'),
        )
        .map(() => `${path}: a Content without the return-focus handlers`)
        .concat(source.includes('useReturnFocus({') ? [] : [`${path}: never calls useReturnFocus`]);
    });
    expect(offenders).toEqual([]);
  });

  it('lets nothing in the app reach the Radix dialog directly', () => {
    const offenders = APP.filter(([, source]) => RADIX_DIALOG.test(source)).map(([path]) => path);
    expect(offenders).toEqual([]);
  });
});

/*
 * Every layout that puts navigation ahead of its `<main>` opens with the skip link, and its `<main>` is
 * a place focus can land. Derived from the route tree: any `layout.tsx` rendering a `<main` is in the
 * population, and leaving one out takes a written reason below.
 */
describe('every layout with a main offers a way to skip to it', () => {
  // Layouts whose `<main>` is the first thing on the page, so there is nothing to skip.
  const NOTHING_BEFORE_MAIN: Record<string, string> = {
    [join('apps', 'web', 'app', '(auth)', 'layout.tsx')]:
      'the auth card IS the main; no navigation precedes it',
  };

  // The element itself, not a mention of it in a comment (those are written in backticks).
  const MAIN_ELEMENT = /(?<!`)<main[\s>]/g;
  const layouts = readSources(join(WEB, 'app'), ['layout.tsx']).filter(
    ([, source]) => source.search(MAIN_ELEMENT) !== -1,
  );

  it('finds the layouts', () => {
    expect(layouts.length).toBeGreaterThanOrEqual(3);
  });

  it('renders the skip link ahead of a main that can take focus', () => {
    const offenders = layouts
      .filter(([path]) => !(path in NOTHING_BEFORE_MAIN))
      .flatMap(([path, source]) => {
        const main = openingTags(source, MAIN_ELEMENT)[0] ?? '';
        const problems: string[] = [];
        if (!/<SkipLink\s*\/>/.test(source)) problems.push(`${path}: no <SkipLink />`);
        else if (source.indexOf('<SkipLink') > source.search(MAIN_ELEMENT))
          problems.push(`${path}: the skip link comes after the main`);
        if (!main.includes('id={MAIN_CONTENT_ID}')) problems.push(`${path}: main has no target id`);
        if (!main.includes('tabIndex={-1}')) problems.push(`${path}: main cannot take focus`);
        return problems;
      });
    expect(offenders).toEqual([]);
  });

  it('keeps every exemption pointing at a real layout', () => {
    // A stale entry would silently exempt a layout later re-created at that path.
    const paths = layouts.map(([path]) => path);
    expect(Object.keys(NOTHING_BEFORE_MAIN).filter((path) => !paths.includes(path))).toEqual([]);
  });
});
