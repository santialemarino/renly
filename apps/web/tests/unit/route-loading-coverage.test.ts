import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * Every protected route has a loading state, and the loading state belongs to THAT route.
 *
 * The population is derived: every `page.tsx` under `app/(protected)`, found by walking the tree, so a
 * route added tomorrow is covered by default and fails here until it has a `loading.tsx`.
 *
 * The rule is "a `loading.tsx` in the page's OWN directory", and not the weaker "one at or above it",
 * because Next renders the NEAREST boundary above a segment. `accounts/loading.tsx` alone would satisfy
 * the weaker rule for `accounts/[id]` — and would paint the ACCOUNTS LIST's header, "Accounts", over a
 * page whose header is about to be the account's own name, then swap it. A loading state that names the wrong
 * page is worse than none; a single `(protected)/loading.tsx` would satisfy the weaker rule for every
 * route at once and be exactly that.
 *
 * And the header it paints must be the page's own. Where the page renders
 * `<PageHeader title={t('title')} …>` from a `getTranslations('<ns>')`, the loading state must pass
 * `namespace="<ns>"`; where the page's title is data (an account's name, a pot's label in a wizard's
 * subtitle), it must pass no namespace at all, since any static title would be a claim about the page
 * that the page then contradicts.
 */

const here = dirname(fileURLToPath(import.meta.url));
const PROTECTED = join(here, '..', '..', 'app', '(protected)');

// The shared component every loading state renders, imported from its one home.
const SKELETON_IMPORT =
  "import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';";

// Every directory under app/(protected) holding a page.tsx, relative to it ('' is not possible — the
// group root has no page).
function protectedPageDirs(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry === 'page.tsx') out.push(relative(PROTECTED, dir));
    }
  };
  walk(PROTECTED);
  return out.sort();
}

interface PageHeaderCopy {
  // The namespace the title is `t('title')` from, or null when the title is not a static translation.
  namespace: string | null;
  // Whether the subtitle is that same translator's `t('subtitle')`, i.e. what the skeleton paints.
  staticSubtitle: boolean;
}

/*
 * What a page's header is made of, read from every `<PageHeader …/>` tag's own props (a page can have
 * two — a dashboard's load-error branch renders its own). The title counts as static only if every tag
 * takes it from `t('title')` of one namespace, and the subtitle only if every tag also uses that
 * translator's `t('subtitle')` — one data-driven branch is enough to make the loading copy a claim.
 */
function pageHeaderCopy(source: string): PageHeaderCopy {
  const tags: string[] = [];
  for (
    let at = source.indexOf('<PageHeader');
    at !== -1;
    at = source.indexOf('<PageHeader', at + 1)
  ) {
    tags.push(source.slice(at, source.indexOf('/>', at)));
  }
  const titles = tags.map((tag) => /^<PageHeader\s+title=\{(\w+)\('title'\)\}/.exec(tag)?.[1]);
  const name = titles[0];
  if (!name || titles.some((t) => t !== name)) return { namespace: null, staticSubtitle: false };
  const subtitle = new RegExp(`\\ssubtitle=\\{${name}\\('subtitle'\\)\\}`);
  return {
    namespace: pageHeaderNamespace(source, name),
    staticSubtitle: tags.every((tag) => subtitle.test(tag)),
  };
}

// The namespace bound to translator `name` in a page.
function pageHeaderNamespace(source: string, name: string): string {
  const translator = new RegExp(`const ${name} = await getTranslations\\('([^']+)'\\)`).exec(
    source,
  );
  // A header built from a translator this scan cannot find is a scan failure, not a dynamic title.
  if (!translator) throw new Error(`PageHeader uses ${name}() but no getTranslations binds it`);
  return translator[1]!;
}

// The `namespace` a loading.tsx passes to PageSkeleton, or null when it passes none.
function loadingNamespace(source: string): string | null {
  return /<PageSkeleton\b[^>]*\bnamespace="([^"]+)"/.exec(source)?.[1] ?? null;
}

// A dotted path into a messages object.
function lookup(messages: unknown, path: string): unknown {
  return path
    .split('.')
    .reduce<unknown>(
      (node, key) =>
        node && typeof node === 'object' ? (node as Record<string, unknown>)[key] : undefined,
      messages,
    );
}

const PAGE_DIRS = protectedPageDirs();

describe('protected route loading coverage', () => {
  it('derives a population that includes nested and dynamic routes', () => {
    // If the walk silently stopped at the first level, every assertion below would pass on a subset.
    expect(PAGE_DIRS).toContain('expenses');
    expect(PAGE_DIRS).toContain('accounts/[id]');
    expect(PAGE_DIRS).toContain('shared/pots/[id]/contribute');
  });

  it.each(PAGE_DIRS)('%s has its own loading.tsx rendering the shared skeleton', (dir) => {
    const loadingPath = join(PROTECTED, dir, 'loading.tsx');
    expect(existsSync(loadingPath), `app/(protected)/${dir}/loading.tsx is missing`).toBe(true);

    const source = readFileSync(loadingPath, 'utf8');
    expect(source).toContain(SKELETON_IMPORT);
    expect(source).toMatch(/return \(?\s*<PageSkeleton\b/);
  });

  it.each(PAGE_DIRS)('%s paints its own header while loading', (dir) => {
    const page = readFileSync(join(PROTECTED, dir, 'page.tsx'), 'utf8');
    const loading = readFileSync(join(PROTECTED, dir, 'loading.tsx'), 'utf8');

    const { namespace: expected, staticSubtitle } = pageHeaderCopy(page);
    expect(loadingNamespace(loading)).toBe(expected);
    // A static title over a data-driven subtitle (a filter's name) must not paint the default subtitle.
    const expectsDataSubtitle = expected !== null && !staticSubtitle;
    expect(/<PageSkeleton\b[^>]*\bsubtitleIsData\b/.test(loading)).toBe(expectsDataSubtitle);

    if (expected !== null) {
      for (const messages of [en, es]) {
        expect(typeof lookup(messages, `${expected}.title`)).toBe('string');
        expect(typeof lookup(messages, `${expected}.subtitle`)).toBe('string');
      }
    }
  });

  it.each(PAGE_DIRS)('%s names toolbar labels that exist in both locales', (dir) => {
    // A missing key renders its own path invisibly, sizing the placeholder by the wrong text.
    const loading = readFileSync(join(PROTECTED, dir, 'loading.tsx'), 'utf8');
    const keys = [
      ...[...loading.matchAll(/\blabel: '([^']+)'/g)].map((m) => m[1]!),
      ...[...loading.matchAll(/\blabels: \[([^\]]*)\]/g)].flatMap((m) =>
        [...m[1]!.matchAll(/'([^']+)'/g)].map((k) => k[1]!),
      ),
    ];
    for (const key of keys) {
      for (const messages of [en, es]) expect(typeof lookup(messages, key), key).toBe('string');
    }
  });

  it('tells a static header from a data-driven one on real pages', () => {
    // Both branches of the namespace check must actually be exercised, or one of them is vacuous.
    const kinds = PAGE_DIRS.map((dir) =>
      pageHeaderCopy(readFileSync(join(PROTECTED, dir, 'page.tsx'), 'utf8')),
    );
    expect(kinds).toContainEqual({ namespace: 'expenses', staticSubtitle: true });
    expect(kinds).toContainEqual({ namespace: 'investorDashboard', staticSubtitle: false });
    expect(kinds).toContainEqual({ namespace: null, staticSubtitle: false });
  });
});
