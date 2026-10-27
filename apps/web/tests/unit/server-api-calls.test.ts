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
 * in the browser, so every module that imports one of them must be a client component.
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

// The names each module imports from the browser module, as values (type-only imports carry no call).
function browserModuleImports(): { file: string; names: string[] }[] {
  return FILES.flatMap((file) =>
    [...read(file).matchAll(/import\s+(type\s+)?\{([^}]*)\}\s+from\s+'@\/lib\/auth-api'/g)]
      .filter((match) => !match[1])
      .map((match) => ({
        file,
        names: (match[2] ?? '')
          .split(',')
          .map((name) => name.trim())
          .filter((name) => name && !name.startsWith('type '))
          .map((name) => name.split(/\s+as\s+/)[0] as string),
      })),
  );
}

describe('server-side API calls', () => {
  it('derives a population to check', () => {
    const sites = helperSites();
    console.info(
      `[server-api-calls] ${sites.length} helper call sites, browser calls: ${browserCalls().join(', ')}`,
    );
    expect(sites.length).toBeGreaterThan(0);
    expect(browserCalls().length).toBeGreaterThan(0);
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
      .filter(({ file }) => !/^\s*'use client';/.test(read(file)))
      .flatMap(({ file, names }) =>
        names.filter((name) => calls.has(name)).map((name) => `${file}: ${name}`),
      );
    expect(serverImports, 'a server-side caller must use lib/auth-api-server.ts').toEqual([]);
  });

  it('the browser module never reads the secret', () => {
    expect(read(BROWSER_MODULE)).not.toMatch(/INTERNAL_API_SECRET/);
  });
});
