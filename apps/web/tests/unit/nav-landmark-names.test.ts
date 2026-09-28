import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/*
 * Every navigation landmark carries a name.
 *
 * The axe sweep cannot hold this on its own: `landmark-unique` fires only when two landmarks of a role
 * share a name, so a page with one named `<nav>` and one unnamed passes it — removing the footer nav's
 * label left the whole sweep green. A reader listing landmarks then hears "navigation" with nothing
 * to tell it apart. So the source is read instead: every `<nav>` opening tag, and every element given
 * `role="navigation"`, in the app and in `packages/ui`, must say `aria-label` or `aria-labelledby`.
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');
const REPO = join(WEB, '..', '..');

function sources(root: string): [string, string][] {
  const out: [string, string][] = [];
  for (const entry of readdirSync(root)) {
    if (entry === 'node_modules' || entry.startsWith('.')) continue;
    const full = join(root, entry);
    if (statSync(full).isDirectory()) out.push(...sources(full));
    else if (entry.endsWith('.tsx')) out.push([relative(REPO, full), readFileSync(full, 'utf8')]);
  }
  return out;
}

// Each JSX opening tag matching `start`, up to the `>` that closes it at brace depth zero.
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

const FILES = [
  ...sources(join(WEB, 'app')),
  ...sources(join(WEB, 'components')),
  ...sources(join(REPO, 'packages', 'ui', 'src')),
];

// The navigation landmarks: `<nav …>` tags, and any tag giving itself role="navigation". Comments are
// dropped first, since prose about a `<nav>` is not one (JSX comments are block comments too).
function landmarks(raw: string): string[] {
  const source = raw.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
  return [
    ...openingTags(source, /<nav\b/g),
    ...openingTags(source, /<[A-Za-z][\w.]*\b(?=[^>]*role="navigation")/g).filter(
      (tag) => !tag.startsWith('<nav'),
    ),
  ];
}

const named = (tag: string) => /\baria-label(ledby)?=/.test(tag);

describe('navigation landmarks', () => {
  const found = FILES.flatMap(([file, source]) => landmarks(source).map((tag) => ({ file, tag })));

  it('finds the landmarks the app renders', () => {
    // Premise: the population is real — the public header and footer, the pagination and the
    // desktop sidebar all render one.
    const files = found.map(({ file }) => file);
    expect(files).toEqual(
      expect.arrayContaining([
        expect.stringContaining('public-header.tsx'),
        expect.stringContaining('public-footer.tsx'),
        expect.stringContaining('pagination.tsx'),
        expect.stringContaining('sidebar.tsx'),
      ]),
    );
  });

  it('names every one', () => {
    expect(
      found.filter(({ tag }) => !named(tag)).map(({ file, tag }) => `${file}: ${tag}`),
    ).toEqual([]);
  });
});
