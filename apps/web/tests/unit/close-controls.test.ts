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

// Every .tsx under `root`, skipping dependencies, build output and dot-folders.
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

/*
 * The local names a file gives lucide's ✕ (`X`, `XIcon`), aliases included: `import { X as Close }`
 * renders `<Close />`, which a search for `<X` would never see.
 */
function lucideXNames(source: string): string[] {
  return [
    ...source.matchAll(/import\s*(?:type\s*)?\{([^}]*)\}\s*from\s*['"]lucide-react['"]/g),
  ].flatMap(([, specifiers = '']) =>
    specifiers
      .split(',')
      .map((specifier) => specifier.trim().split(/\s+as\s+/))
      .filter(([imported]) => imported === 'X' || imported === 'XIcon')
      .map(([imported, local]) => local ?? imported ?? ''),
  );
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

/*
 * The whole web app (not only `app/` and `components/`: a ✕ in `lib/` or a new top-level folder renders
 * just the same) and `packages/ui/src`. The tests themselves are left out — they render nothing.
 */
const SOURCES = [
  ...readSources(WEB).filter(([path]) => !path.startsWith(join('apps', 'web', 'tests'))),
  ...readSources(join(REPO, 'packages', 'ui', 'src')),
];
const KINDS = Object.keys(CLOSE_CONTROL);
// A JSX element or an `icon={…}` prop rendering one of these names.
const tagOf = (names: string[]) => new RegExp(`<(?:${names.join('|')})\\b`, 'g');
const iconPropOf = (names: string[]) => new RegExp(`icon=\\{(?:${names.join('|')})\\}`, 'g');

describe('every ✕ is one of the close-control kinds', () => {
  const withX = SOURCES.map(
    ([path, source]) => [path, source, lucideXNames(source)] as const,
  ).filter(([, , names]) => names.length > 0);

  it('sees a ✕ imported under another name', () => {
    expect(lucideXNames("import { Check, X as Close } from 'lucide-react';")).toEqual(['Close']);
    expect(lucideXNames("import {\n  XIcon,\n  Plus,\n} from 'lucide-react';")).toEqual(['XIcon']);
    expect(lucideXNames("import { XCircle } from 'lucide-react';")).toEqual([]);
  });

  it('finds the ✕s', () => {
    // Dialog, sheet, search clear, hint dismiss, chip remove, currency clear, the onboarding card's
    // dismiss and the group invite's revoke row action today: fewer means the walk broke.
    expect(withX.length).toBeGreaterThanOrEqual(8);
  });

  it('styles each rendered ✕ icon with its kind’s icon classes', () => {
    const offenders = withX.flatMap(([path, source, names]) =>
      openingTags(source, tagOf(names))
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
      (count, [, source, names]) => count + openingTags(source, tagOf(names)).length,
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
    const offenders = withX.flatMap(([path, source, names]) =>
      [...source.matchAll(iconPropOf(names))]
        .filter((match) => {
          const before = source.slice(0, match.index);
          return !/<RowActionButton\b[^<]*$/.test(before);
        })
        .map(() => path),
    );
    expect(offenders).toEqual([]);
  });
});
