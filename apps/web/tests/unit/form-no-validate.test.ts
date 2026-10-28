import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/*
 * Every `<form>` carries `noValidate`. Our forms validate with their own schemas and show our own
 * localized messages under each field; without the attribute the browser runs its constraint
 * validation first on any `required` / `type="email"` / `min` input and shows its own bubble, in the
 * browser's language, before our handler ever runs. Four forms shipped without it.
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');
const REPO = join(WEB, '..', '..');

function readSources(root: string): [string, string][] {
  const out: [string, string][] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      if (entry === 'node_modules' || entry.startsWith('.')) continue;
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry.endsWith('.tsx')) out.push([relative(REPO, full), readFileSync(full, 'utf8')]);
    }
  };
  walk(root);
  return out;
}

// Comments mention `<form>` in prose; blanked so only real tags are read.
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}

/*
 * Each `<form` opening tag, up to the `>` that closes it — found by tracking brace depth, because a
 * prop like `onSubmit={(e) => …}` carries a `>` of its own.
 */
function formTags(source: string): string[] {
  return [...source.matchAll(/<form(?=[\s>])/g)].map((match) => {
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

const FORMS = [
  ...readSources(join(WEB, 'app')),
  ...readSources(join(WEB, 'components')),
  ...readSources(join(REPO, 'packages', 'ui', 'src')),
].flatMap(([path, source]) => formTags(stripComments(source)).map((tag) => [path, tag] as const));

describe('every form opts out of native validation', () => {
  it('finds the forms', () => {
    // A guard on the guard: an empty walk would pass the assertion below.
    expect(FORMS.length).toBeGreaterThan(30);
  });

  it('sets noValidate on every <form>', () => {
    const missing = FORMS.filter(([, tag]) => !/\bnoValidate\b/.test(tag)).map(([path]) => path);
    expect(missing).toEqual([]);
  });
});
