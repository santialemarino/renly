import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * Structural guards over ACCESSIBLE NAMES, and they read source text rather than importing anything.
 *
 * Every check below is a set difference across two artifacts that have to agree, because the failure
 * this file exists for is the two drifting apart rather than either one being wrong on its own. A
 * per-call-site assertion would agree with itself forever: it stops being asked the moment somebody
 * adds a call site it was never written about, which is exactly how fifty-five hardcoded English
 * aria-labels accumulated behind fifty-five translated tooltips, thirteen of them already saying
 * something different from the tooltip beside them.
 *
 * Source text, not imports: `packages/ui` is only exported as a whole barrel, so importing it here
 * would drag every Radix primitive into a node-project test to read eight object keys — and reading
 * the OTHER side's source is the property that makes these guards worth having (a test that restates
 * what it is checking passes on the copy it made, not on the thing).
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');
const REPO = join(WEB, '..', '..');
const UI = join(REPO, 'packages', 'ui', 'src');

function readTsx(root: string, skip: (path: string) => boolean = () => false): [string, string][] {
  const out: [string, string][] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      if (entry === 'node_modules' || entry.startsWith('.')) continue;
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry.endsWith('.tsx') && !skip(full))
        out.push([relative(REPO, full), readFileSync(full, 'utf8')]);
    }
  };
  walk(root);
  return out;
}

// Every JSX element of the given name, from its opening `<` to the `/>` that closes the self-closing
// tag (all three components below are always self-closing) — enough to read its attributes.
// Captures the first group of every match, dropping the `string | undefined` an optional group would
// imply — every pattern below has exactly one mandatory group.
function captures(source: string, pattern: RegExp): string[] {
  return [...source.matchAll(pattern)].map((match) => match[1] ?? '');
}

function elements(source: string, name: string): string[] {
  const found: string[] = [];
  const opening = new RegExp(`<${name}\\b`, 'g');
  let match: RegExpExecArray | null;
  while ((match = opening.exec(source)) !== null) {
    const end = source.indexOf('/>', match.index);
    if (end !== -1) found.push(source.slice(match.index, end + 2));
  }
  return found;
}

const APP_SOURCES = readTsx(WEB, (path) => path.includes(`${join('tests', '')}`));
const UI_SOURCES = readTsx(UI);

describe('no accessible name is a hardcoded string', () => {
  it('finds sources to check', () => {
    // A guard on the guards: were the walk to return nothing, every assertion here would pass empty.
    expect(APP_SOURCES.length).toBeGreaterThan(100);
    expect(UI_SOURCES.length).toBeGreaterThan(10);
  });

  it('has no literal aria-label anywhere in the app', () => {
    const offenders = APP_SOURCES.flatMap(([path, source]) =>
      captures(source, /aria-label="([^"]*)"/g).map((value) => `${path}: ${value}`),
    );
    expect(offenders).toEqual([]);
  });

  /*
   * The three shared primitives that take a name as a prop. Their props are an explicit list rather
   * than React's, so a literal here type-checks perfectly — nothing but this notices.
   */
  it.each([
    ['RowActionButton', ['tooltip']],
    ['RowLockedIndicator', ['tooltip', 'label']],
    ['CopyButton', ['ariaLabel']],
  ] as const)('passes %s a translated value, never a literal', (component, props) => {
    const offenders = APP_SOURCES.flatMap(([path, source]) =>
      elements(source, component).flatMap((element) =>
        props
          .filter((prop) => new RegExp(`\\b${prop}="`).test(element))
          .map((prop) => `${path}: ${component} ${prop}=`),
      ),
    );
    expect(offenders).toEqual([]);
  });

  /*
   * @repo/ui cannot call a translator — it is a design-system package with no i18n layer, deliberately
   * — so the names it renders itself come from UiLabelsProvider. A literal that slips back in here is
   * invisible to the app: it renders English under a Spanish locale with nothing failing.
   */
  it('leaves no literal aria-label or sr-only text in packages/ui', () => {
    const offenders = UI_SOURCES.filter(([path]) => !path.endsWith('ui-labels.tsx')).flatMap(
      ([path, source]) => [
        ...captures(source, /aria-label="([^"]*)"/g).map(
          (value) => `${path}: aria-label="${value}"`,
        ),
        // Non-whitespace first, or the newline before a nested element reads as visually-hidden text.
        ...captures(source, /className="[^"]*sr-only[^"]*">\s*([^<{\s][^<{]*)</g).map(
          (value) => `${path}: sr-only "${value.trim()}"`,
        ),
      ],
    );
    expect(offenders).toEqual([]);
  });
});

/*
 * An icon-only button has no text to fall back on, so a missing `aria-label` leaves a screen reader
 * announcing "button" and nothing else. That is not the drift the guards above are about — it is the
 * absence a "no literal" rule structurally cannot see, because there is nothing there to inspect.
 *
 * Found by exactly this scan while measuring the sweep: one button, on the integrations page, had gone
 * unnamed since it was written. A set difference rather than a list of known buttons, so the next one
 * added is checked the day it lands.
 */
describe('every icon-only button says what it does', () => {
  // The opening tag plus its children, for a <Button> that is not self-closing.
  function iconButtons(source: string) {
    const found: { opening: string; body: string }[] = [];
    for (const match of source.matchAll(/<Button\b/g)) {
      let depth = 0;
      let cursor = match.index;
      while (cursor < source.length) {
        const char = source[cursor];
        if (char === '{') depth += 1;
        else if (char === '}') depth -= 1;
        else if (char === '>' && depth === 0) break;
        cursor += 1;
      }
      const opening = source.slice(match.index, cursor + 1);
      if (opening.trimEnd().endsWith('/>')) continue;
      const close = source.indexOf('</Button>', cursor);
      found.push({ opening, body: close === -1 ? '' : source.slice(cursor + 1, close) });
    }
    return found.filter(({ opening }) => opening.includes('size="icon'));
  }

  // Anything that is not a tag, a JSX comment or whitespace — i.e. words a user could read.
  const visibleText = (body: string) =>
    body
      .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
      .replace(/<[^>]*>/g, '')
      .trim();

  it('finds icon buttons to check', () => {
    expect(APP_SOURCES.flatMap(([, source]) => iconButtons(source)).length).toBeGreaterThan(5);
  });

  it('names every one of them', () => {
    const unnamed = APP_SOURCES.flatMap(([path, source]) =>
      iconButtons(source)
        .filter(
          ({ opening, body }) =>
            !opening.includes('aria-label') &&
            !opening.includes('aria-labelledby') &&
            !visibleText(body),
        )
        .map(() => path),
    );
    expect(unnamed).toEqual([]);
  });
});

/*
 * A locked row's two strings are a short name and a long explanation, and the naming convention is
 * what keeps them apart: the name lives at `<reason>Label`, the sentence at `<reason>`. Passing the
 * sentence key as the name type-checks, reads fine in a diff, and makes a screen reader say the whole
 * sentence twice — once as the element's name and once as the tooltip's description.
 */
describe('a locked row names itself from a *Label key', () => {
  const labelProps = APP_SOURCES.flatMap(([path, source]) =>
    elements(source, 'RowLockedIndicator').map((element) => ({
      path,
      value: /\blabel=\{([\s\S]*?)\}\s*(?:\n|\/>)/.exec(element)?.[1] ?? '',
    })),
  );

  it('finds every locked indicator', () => {
    expect(labelProps.length).toBeGreaterThan(5);
    expect(labelProps.filter(({ value }) => !value)).toEqual([]);
  });

  it('resolves a key ending in Label at every one of them', () => {
    expect(labelProps.filter(({ value }) => !value.includes('Label')).map((p) => p.path)).toEqual(
      [],
    );
  });
});

/*
 * The UI label set, stated in four places that must agree: the package's defaults, both locales, and
 * the one place the app wires them. tsc catches a label USED but not declared; nothing else catches a
 * label declared and then not translated, or translated and never passed — both of which leave the
 * English default rendering under a Spanish locale, silently.
 */
describe('packages/ui label set', () => {
  // The object literal between a known opening line and the `};` that closes it.
  const objectBody = (source: string, opening: string) =>
    (source.split(opening)[1] ?? '').split('};')[0] ?? '';

  const declared = captures(
    objectBody(
      readFileSync(join(UI, 'components', 'ui-labels.tsx'), 'utf8'),
      'export const DEFAULT_UI_LABELS',
    ),
    /^\s{2}(\w+):/gm,
  );

  const wired = captures(
    objectBody(readFileSync(join(WEB, 'app', 'layout.tsx'), 'utf8'), 'const uiLabels = {'),
    /^\s{4}(\w+):/gm,
  );

  it('parsed a non-empty set from each source', () => {
    expect(declared.length).toBeGreaterThan(5);
    expect(wired.length).toBeGreaterThan(5);
  });

  it.each(['en', 'es'])('translates every label the package declares, in %s', (locale) => {
    const ui = (locale === 'en' ? en : es).common.ui as Record<string, string>;
    expect(declared.filter((key) => !ui[key])).toEqual([]);
  });

  it('has no translated label the package does not declare', () => {
    const known = new Set(declared);
    expect(Object.keys(en.common.ui).filter((key) => !known.has(key))).toEqual([]);
  });

  it('wires every declared label in the root layout', () => {
    // The direction that actually bites: a label added to the package and translated, but never
    // passed, keeps rendering its English default under every locale.
    const passed = new Set(wired);
    expect(declared.filter((key) => !passed.has(key))).toEqual([]);
  });
});

/*
 * A locked row says two things: WHAT is withheld (the accessible name) and WHY (the tooltip, which
 * Radix announces as the description on focus). They are separate strings on purpose, so a missing
 * label is a real gap rather than a duplicate — and next-intl answers a missing key with the key path
 * itself, a non-empty string, so a reader would simply hear "lockedRow.sharedHoldingLabel".
 */
describe('locked-row labels', () => {
  const reasons = (locale: 'en' | 'es') =>
    Object.keys((locale === 'en' ? en : es).common.lockedRow).filter(
      (key) => !key.endsWith('Label'),
    );

  it.each(['en', 'es'] as const)('names every locked-row reason in %s', (locale) => {
    const messages = (locale === 'en' ? en : es).common.lockedRow as Record<string, string>;
    expect(reasons(locale).filter((reason) => !messages[`${reason}Label`])).toEqual([]);
  });

  it('has no label left behind by a reason that is gone', () => {
    const known = new Set(reasons('en').map((reason) => `${reason}Label`));
    const labels = Object.keys(en.common.lockedRow).filter((key) => key.endsWith('Label'));
    expect(labels.filter((label) => !known.has(label))).toEqual([]);
  });
});

/*
 * Radix warns in the console for a dialog with no description, which is a warning nobody reads and a
 * screen-reader user's missing context. Both answers are fine — describe it, or say plainly that it
 * has nothing to add — and this only forbids the third one, which is saying nothing at all.
 */
describe('every dialog answers the description question', () => {
  const contents = APP_SOURCES.flatMap(([path, source]) =>
    [...source.matchAll(/<DialogContent\b/g)].map((match) => {
      const end = source.indexOf('</DialogContent>', match.index);
      return {
        where: `${path}:${source.slice(0, match.index).split('\n').length}`,
        block: source.slice(match.index, end === -1 ? undefined : end),
      };
    }),
  );

  it('finds dialogs to check', () => {
    expect(contents.length).toBeGreaterThan(30);
  });

  it('gives each one a DialogDescription or an explicit opt-out', () => {
    const silent = contents
      .filter(
        ({ block }) =>
          // The opening TAG, not the bare word: matching the word passes on a block whose
          // <DialogDescription> was reverted to a plain <p> and whose closing tag was left behind —
          // which a mutation sweep proved, and which is the shape the promoted paragraphs came from.
          !block.includes('<DialogDescription') && !block.includes('aria-describedby={undefined}'),
      )
      .map(({ where }) => where);
    expect(silent).toEqual([]);
  });
});
