import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
  A11Y_ALLOW_LIST,
  allowListProblems,
  type A11yAllowListEntry,
} from '../e2e/helpers/a11y-allowlist';

/*
 * The accessibility allow-list stays honest: no entry outlives its date, and none points at an element
 * nothing renders any more. See `tests/e2e/helpers/a11y-allowlist.ts` for why each rule exists.
 *
 * The list is empty, so checking only the real entries would pass whatever the validator did. The
 * first block therefore drives the validator with entries built to break each rule, and the second
 * runs it on the real list.
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');
const UI = join(WEB, '..', '..', 'packages', 'ui', 'src');

function sourcesUnder(root: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(root)) {
    if (entry === 'node_modules' || entry.startsWith('.')) continue;
    const full = join(root, entry);
    if (statSync(full).isDirectory()) out.push(...sourcesUnder(full));
    else if (/\.tsx?$/.test(entry)) out.push(readFileSync(full, 'utf8'));
  }
  return out;
}

// Where an allow-listed selector may point: what the app and the design system render.
const SOURCES = [
  ...sourcesUnder(join(WEB, 'app')),
  ...sourcesUnder(join(WEB, 'components')),
  ...sourcesUnder(UI),
];

const TODAY = new Date().toISOString().slice(0, 10);
const NEXT_YEAR = `${new Date().getUTCFullYear() + 1}-01-01`;

// A valid entry, pointing at a testid the app really renders.
const VALID: A11yAllowListEntry = {
  rule: 'color-contrast',
  selector: '[data-testid="currency-switcher"]',
  reason: 'A worked example for the validator, never a real exception.',
  revisitBy: NEXT_YEAR,
};

describe('the allow-list validator', () => {
  it('accepts a well-formed entry that points at something rendered', () => {
    // Premise: the testid the example names is really in the source, so the cases below fail for the
    // reason each names and not because this one would.
    expect(allowListProblems([VALID], TODAY, SOURCES)).toEqual([]);
  });

  it('refuses an entry past its date', () => {
    const problems = allowListProblems([{ ...VALID, revisitBy: '2020-01-01' }], TODAY, SOURCES);
    expect(problems).toEqual([expect.stringContaining('has passed')]);
  });

  it('refuses a selector nothing renders any more', () => {
    const problems = allowListProblems(
      [{ ...VALID, selector: '[data-testid="no-component-renders-this"]' }],
      TODAY,
      SOURCES,
    );
    expect(problems).toEqual([expect.stringContaining('nothing renders')]);
  });

  it('refuses a selector it cannot check against the source', () => {
    const problems = allowListProblems([{ ...VALID, selector: '.text-blue-400' }], TODAY, SOURCES);
    expect(problems).toEqual([expect.stringContaining('must name a [data-testid]')]);
  });

  it('refuses a missing reason, a malformed date and a made-up rule', () => {
    const problems = allowListProblems(
      [{ ...VALID, rule: 'Color Contrast', reason: 'tbd', revisitBy: 'soon' }],
      TODAY,
      SOURCES,
    );
    expect(problems).toHaveLength(3);
  });
});

describe('the allow-list', () => {
  it('holds no expired, stale or malformed entry', () => {
    expect(allowListProblems(A11Y_ALLOW_LIST, TODAY, SOURCES)).toEqual([]);
  });
});
