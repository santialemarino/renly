import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/*
 * Every call this server makes to the API goes through serverApiFetch, which names the visitor the
 * call is for — so the API rate-limits the visitor, not this server. A call that forgot it would put
 * every visitor's login (or refresh, or signup read) into one shared bucket again.
 *
 * The population is derived, not listed: every raw `fetch(` in the app's source must sit either in
 * the helper itself or in the browser auth module (`lib/auth-api.ts`), whose calls the browser makes
 * directly and which therefore never see the secret. That exemption holds only while those calls stay
 * in the browser, so every module that imports one of them must be a client component — however it
 * imports it (named, namespace or dynamic, through the alias or a relative path) — and no module may
 * re-export one, which would hide the real caller from this check.
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');
const HELPER = 'lib/server-api-fetch.ts';
const BROWSER_MODULE = 'lib/auth-api.ts';
const SKIPPED_DIRS = new Set(['node_modules', '.next', 'tests', 'public', 'test-results']);

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return SKIPPED_DIRS.has(entry) ? [] : sourceFiles(full);
    return /\.tsx?$/.test(entry) && !entry.endsWith('.d.ts') ? [relative(WEB, full)] : [];
  });
}

const FILES = sourceFiles(WEB);
const read = (file: string) => readFileSync(join(WEB, file), 'utf8');

// Every raw fetch call site, as `file:line`.
function rawFetchSites(): string[] {
  return FILES.flatMap((file) =>
    read(file)
      .split('\n')
      .flatMap((line, index) => (/\bfetch\(/.test(line) ? [`${file}:${index + 1}`] : [])),
  );
}

// Every call site of the helper (directly, or through authenticatedFetch, which wraps it).
function helperSites(): string[] {
  return FILES.flatMap((file) =>
    read(file)
      .split('\n')
      .flatMap((line, index) =>
        /\b(serverApiFetch|authenticatedFetch)\(/.test(line) && !/function /.test(line)
          ? [`${file}:${index + 1}`]
          : [],
      ),
  );
}

// The browser module's exported functions that call the API.
function browserCalls(): string[] {
  const source = read(BROWSER_MODULE);
  const exported = [...source.matchAll(/^export async function (\w+)/gm)];
  return exported.flatMap((match, i) => {
    const body = source.slice(match.index, exported[i + 1]?.index ?? source.length);
    return /\bfetch\(/.test(body) ? [match[1] as string] : [];
  });
}

const BROWSER_MODULE_ID = BROWSER_MODULE.replace(/\.tsx?$/, '');

// Whether a module specifier written in `file` names the browser module: through the `@/` alias or a
// relative path, with or without its extension (`lib/auth-api-server` is a different module).
function isBrowserModule(file: string, specifier: string): boolean {
  let target: string;
  if (specifier.startsWith('@/')) target = specifier.slice(2);
  else if (specifier.startsWith('.')) target = relative(WEB, join(WEB, dirname(file), specifier));
  else return false;
  return target.replace(/\.tsx?$/, '') === BROWSER_MODULE_ID;
}

// A static import or re-export: `import { a }`, `import * as ns`, `import x, { a }`, `export { a }`,
// `export * from`. Type-only statements carry no call and are skipped.
const STATEMENT =
  /\b(import|export)\s+(type\s+)?(\*(?:\s+as\s+\w+)?|\{[^}]*\}|\w+(?:\s*,\s*(?:\{[^}]*\}|\*\s+as\s+\w+))?)\s+from\s+['"]([^'"]+)['"]/g;
const DYNAMIC_IMPORT = /\bimport\(\s*['"]([^'"]+)['"]\s*\)/g;

// The names each module takes from the browser module, as values: an import (`kind: 'import'`) or a
// re-export (`kind: 'export'`). A namespace import, `export *` or a dynamic import takes every name.
function browserModuleImports(): { file: string; kind: 'import' | 'export'; names: string[] }[] {
  const everything = browserCalls();
  return FILES.flatMap((file) => {
    const source = read(file);
    const statements = [...source.matchAll(STATEMENT)]
      .filter((match) => !match[2] && isBrowserModule(file, match[4] as string))
      .map((match) => {
        const clause = match[3] as string;
        const braces = clause.match(/\{([^}]*)\}/);
        const names = clause.includes('*')
          ? everything
          : (braces?.[1] ?? '')
              .split(',')
              .map((name) => name.trim())
              .filter((name) => name && !name.startsWith('type '))
              .map((name) => name.split(/\s+as\s+/)[0] as string);
        return { file, kind: match[1] as 'import' | 'export', names };
      });
    const dynamic = [...source.matchAll(DYNAMIC_IMPORT)]
      .filter((match) => isBrowserModule(file, match[1] as string))
      .map(() => ({ file, kind: 'import' as const, names: everything }));
    return [...statements, ...dynamic];
  });
}

describe('server-side API calls', () => {
  it('derives a population to check', () => {
    const sites = helperSites();
    console.info(
      `[server-api-calls] ${sites.length} helper call sites, browser calls: ${browserCalls().join(', ')}, ${browserModuleImports().length} value imports of the browser module`,
    );
    expect(sites.length).toBeGreaterThan(0);
    expect(browserCalls().length).toBeGreaterThan(0);
    expect(browserModuleImports().length).toBeGreaterThan(0);
  });

  it('makes no raw fetch outside the helper and the browser module', () => {
    const stray = rawFetchSites().filter(
      (site) => !site.startsWith(`${HELPER}:`) && !site.startsWith(`${BROWSER_MODULE}:`),
    );
    expect(stray, 'call the API through serverApiFetch (lib/server-api-fetch.ts)').toEqual([]);
  });

  it('the helper is the only raw fetch on the server side and is server-only', () => {
    expect(rawFetchSites().filter((site) => site.startsWith(`${HELPER}:`))).toHaveLength(1);
    expect(read(HELPER)).toMatch(/^import 'server-only';/);
  });

  it("the browser module's calls are imported only by client components", () => {
    const calls = new Set(browserCalls());
    const serverImports = browserModuleImports()
      .filter(({ file, kind }) => kind === 'import' && !/^\s*'use client';/.test(read(file)))
      .flatMap(({ file, names }) =>
        names.filter((name) => calls.has(name)).map((name) => `${file}: ${name}`),
      );
    expect(serverImports, 'a server-side caller must use lib/auth-api-server.ts').toEqual([]);
  });

  it("the browser module's calls are never re-exported", () => {
    const calls = new Set(browserCalls());
    const reExports = browserModuleImports()
      .filter(({ kind }) => kind === 'export')
      .flatMap(({ file, names }) =>
        names.filter((name) => calls.has(name)).map((name) => `${file}: ${name}`),
      );
    expect(
      reExports,
      'import a browser call from lib/auth-api.ts itself, not through a re-export',
    ).toEqual([]);
  });

  it('the browser module never reads the secret', () => {
    expect(read(BROWSER_MODULE)).not.toMatch(/INTERNAL_API_SECRET/);
  });
});
