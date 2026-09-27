import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { protectedPageRoutes, TEXT_SWEEP_SKIPS, textSweepRoutes } from '../e2e/helpers/text-pages';

/*
 * The text sweep visits every page of the app surface. Its page list is derived from the route tree,
 * so what can drift is the rest: a skip naming a page that no longer exists (excusing nothing), or a
 * dynamic route that is neither skipped nor given a URL by the spec (which would throw mid-sweep and
 * report one error for a whole locale).
 */

const here = dirname(fileURLToPath(import.meta.url));
const SPEC = readFileSync(join(here, '..', 'e2e', 'locale-text-clipping.auth.spec.ts'), 'utf8');

// The dynamic routes the spec's `url()` resolves: `if (route === '/accounts/[id]') return …`.
const resolvedDynamic = [...SPEC.matchAll(/route === '([^']*\[[^']*)'\) return/g)].map(
  (match) => match[1],
);

describe('the text sweep’s page list', () => {
  const all = protectedPageRoutes();
  const swept = textSweepRoutes();

  it('derives the real route tree', () => {
    // Route groups dropped, nested and dynamic pages both found — read from the tree, not recalled.
    expect(all).toEqual(
      expect.arrayContaining([
        '/dashboard',
        '/investor-dashboard',
        '/payments-calendar',
        '/accounts/[id]',
        '/shared/pots/[id]/contribute',
      ]),
    );
    expect(all.every((route) => !route.includes('('))).toBe(true);
    expect(swept.length).toBeGreaterThan(20);
  });

  it('skips only pages that exist', () => {
    expect(Object.keys(TEXT_SWEEP_SKIPS).filter((route) => !all.includes(route))).toEqual([]);
  });

  it('gives every swept dynamic route a URL', () => {
    expect(resolvedDynamic).toContain('/accounts/[id]');
    expect(
      swept.filter((route) => route.includes('[') && !resolvedDynamic.includes(route)),
    ).toEqual([]);
  });

  it('never both resolves and skips a dynamic route', () => {
    expect(resolvedDynamic.filter((route) => route! in TEXT_SWEEP_SKIPS)).toEqual([]);
  });
});
