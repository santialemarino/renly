import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { CLOSE_CONTROL } from '@repo/ui/lib';

/*
 * Every ✕ — a control that closes, dismisses, clears or removes — is one of the four kinds in
 * `packages/ui/src/lib/close-control.ts`, and takes that kind's classes from there rather than styling
 * itself. The population is derived: every lucide `X` / `XIcon` rendered as JSX in the app and in
 * `packages/ui`. What these cannot see is the paint (does the ring clear 3:1, does the icon bump);
 * `tests/e2e/focus-system.auth.spec.ts` measures one of each kind in the browser.
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

// Each JSX opening tag matching `start`, up to its closing `>` (brace depth tracked for `=>` in props).
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

const SOURCES = [
  ...readSources(join(WEB, 'app')),
  ...readSources(join(WEB, 'components')),
  ...readSources(join(REPO, 'packages', 'ui', 'src')),
];
const KINDS = Object.keys(CLOSE_CONTROL);
const LUCIDE_X = /import\s*\{[^}]*\b(X|XIcon)\b[^}]*\}\s*from\s*'lucide-react'/;

describe('every ✕ is one of the close-control kinds', () => {
  const withX = SOURCES.filter(([, source]) => LUCIDE_X.test(source));

  it('finds the ✕s', () => {
    // Dialog, sheet, search clear, hint dismiss, chip remove, currency clear, the onboarding card's
    // dismiss and the group invite's revoke row action today: fewer means the walk broke.
    expect(withX.length).toBeGreaterThanOrEqual(8);
  });

  it('styles each rendered ✕ icon with its kind’s icon classes', () => {
    const offenders = withX.flatMap(([path, source]) =>
      openingTags(source, /<(?:X|XIcon)\b/g)
        .filter((tag) => !/className=\{CLOSE_CONTROL\.(\w+)\.icon\}/.test(tag))
        .map((tag) => `${path}: ${tag}`),
    );
    expect(offenders).toEqual([]);
  });

  it('names the kind on the control and takes that kind’s button classes', () => {
    const controls = SOURCES.flatMap(([path, source]) =>
      openingTags(source, /<[A-Z][\w.]*\b|<button\b/g)
        // The tag's OWN attribute, not one on an element nested in a prop (SearchInput's endIcon).
        .filter(
          (tag) =>
            tag.includes('data-close-kind=') &&
            !tag.slice(1, tag.indexOf('data-close-kind=')).includes('<'),
        )
        .map((tag) => [path, tag] as const),
    );
    // One control per rendered ✕ icon: none styled as a ✕ without saying which kind it is.
    const icons = withX.reduce(
      (count, [, source]) => count + openingTags(source, /<(?:X|XIcon)\b/g).length,
      0,
    );
    expect(controls).toHaveLength(icons);
    const offenders = controls.flatMap(([path, tag]) => {
      const kind = /data-close-kind="(\w+)"/.exec(tag)?.[1] ?? '';
      if (!KINDS.includes(kind)) return [`${path}: unknown kind "${kind}"`];
      return tag.includes(`CLOSE_CONTROL.${kind}.button`)
        ? []
        : [`${path}: a "${kind}" control without CLOSE_CONTROL.${kind}.button`];
    });
    expect(offenders).toEqual([]);
  });

  it('leaves a ✕ used as a row action to the row action button', () => {
    // A row action (the group invite's revoke) is a RowActionButton like its siblings — a ghost icon
    // button with the default ring — not a close control.
    const offenders = withX.flatMap(([path, source]) =>
      [...source.matchAll(/icon=\{(?:X|XIcon)\}/g)]
        .filter((match) => {
          const before = source.slice(0, match.index);
          return !/<RowActionButton\b[^<]*$/.test(before);
        })
        .map(() => path),
    );
    expect(offenders).toEqual([]);
  });
});
