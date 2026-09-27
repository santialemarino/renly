import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { LEGEND_ROUTES, MONEY_SWEEP_ROUTES, MONEY_SWEEP_SKIPS } from '../e2e/helpers/money-pages';

/*
 * The money overflow sweep visits every page that renders money, and the list of those pages is
 * DERIVED here rather than trusted.
 *
 * A page counts as money-bearing when one of its OWN files — its folder under `app/(protected)`, not
 * counting a nested folder that is a page of its own — renders `<MoneyFigure` or a shared component
 * that does. Those components are derived too: every file in `components/` whose source renders
 * `<MoneyFigure`, and the components it exports. So a new page showing a figure, or a new shared
 * component wrapping one, joins the population without anyone listing it.
 *
 * Every money-bearing page must then be swept or skipped with a reason, and the two lists must not name
 * a page that is no longer money-bearing — a stale entry is a sweep that checks something that is not
 * there, or a skip excusing nothing.
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');
const PROTECTED = join(WEB, 'app', '(protected)');

// A route group — a `(name)` folder, which wraps its pages without adding a URL segment.
const isRouteGroup = (name: string) => /^\(.+\)$/.test(name);

// Whether a folder is a page's: it holds a page.tsx itself, or one inside a route group of its own
// (a detail page moved into `(hub)/` still owns its folder's `_components`, and nothing above it does).
function isPageFolder(dir: string): boolean {
  if (existsSync(join(dir, 'page.tsx'))) return true;
  return readdirSync(dir).some(
    (entry) => isRouteGroup(entry) && existsSync(join(dir, entry, 'page.tsx')),
  );
}

function tsxUnder(dir: string, stopAtPages: boolean): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (stopAtPages && isPageFolder(full)) continue;
      out.push(...tsxUnder(full, stopAtPages));
    } else if (entry.endsWith('.tsx')) out.push(full);
  }
  return out;
}

/*
 * Every page folder under (protected), as its route pattern. Route-group segments are dropped, as in
 * the URL: a list page whose details live under it sits in one (`accounts/(list)/page.tsx`, so its
 * loading state wraps only that page) and still serves `/accounts`.
 */
function pageRoutes(dir = PROTECTED): [string, string][] {
  const out: [string, string][] = [];
  if (existsSync(join(dir, 'page.tsx'))) {
    const segments = relative(PROTECTED, dir)
      .split(sep)
      .filter((segment) => !isRouteGroup(segment));
    out.push([`/${segments.join('/')}`, dir]);
  }
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory() && !entry.startsWith('_')) out.push(...pageRoutes(full));
  }
  return out;
}

// The JSX tags that put a marked figure on the page: MoneyFigure itself, and every component exported
// from a shared file that renders it.
function moneyTags(): string[] {
  const tags = new Set(['MoneyFigure']);
  tsxUnder(join(WEB, 'components'), false).forEach((file) => {
    const source = readFileSync(file, 'utf8');
    if (!source.includes('<MoneyFigure')) return;
    [...source.matchAll(/export function (\w+)/g)].forEach((match) => tags.add(match[1] ?? ''));
  });
  return [...tags];
}

/*
 * The files a page renders from: its own folder, stopping at nested pages — and, for a page inside a
 * route group, the section folder around the group too, since that is where its `_components` stay.
 */
function pageFiles(dir: string): string[] {
  const files = tsxUnder(dir, true);
  const name = dir.split(sep).pop() ?? '';
  return isRouteGroup(name) ? [...files, ...tsxUnder(dirname(dir), true)] : files;
}

function moneyBearingRoutes(): string[] {
  const tags = moneyTags();
  const renders = (source: string) => tags.some((tag) => new RegExp(`<${tag}\\b`).test(source));
  return pageRoutes()
    .filter(([, dir]) => pageFiles(dir).some((file) => renders(readFileSync(file, 'utf8'))))
    .map(([route]) => route)
    .sort();
}

describe('the money sweep’s page list', () => {
  const derived = moneyBearingRoutes();
  const swept: string[] = [...MONEY_SWEEP_ROUTES];
  const skipped = Object.keys(MONEY_SWEEP_SKIPS);

  it('derives a real population — the shared components and the pages both', () => {
    // The derivation reads what it claims to: the three headline dashboards render MetricCard, which
    // is only in the set because MetricCard's own source renders MoneyFigure.
    expect(moneyTags()).toEqual(
      expect.arrayContaining(['MetricCard', 'SignedAmountCell', 'TableSectionRow']),
    );
    expect(derived).toEqual(
      expect.arrayContaining(['/dashboard', '/finance-dashboard', '/investor-dashboard']),
    );
  });

  it('sweeps or skips every page that renders money', () => {
    expect(derived.filter((route) => !swept.includes(route) && !skipped.includes(route))).toEqual(
      [],
    );
  });

  it('names no page that does not render money', () => {
    expect([...swept, ...skipped].filter((route) => !derived.includes(route))).toEqual([]);
  });

  it('never both sweeps and skips a page', () => {
    expect(swept.filter((route) => skipped.includes(route))).toEqual([]);
  });

  it('checks legends only on pages it sweeps', () => {
    expect(LEGEND_ROUTES.filter((route) => !swept.includes(route))).toEqual([]);
  });
});
