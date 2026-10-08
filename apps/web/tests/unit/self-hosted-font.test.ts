import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

import { WEB_ROOT } from '../e2e/helpers/list-pages';

/*
 * The build must not reach the network for its typeface.
 *
 * `next/font/google` downloads the font while `next build` runs, so a slow or failed fetch from Google
 * Fonts failed the web build on CI with nothing wrong in the code. The face is now a committed file
 * loaded through `next/font/local`, defined ONCE and imported by every document root — the root layout
 * and the global error page, which replaces it. Read from source: the import and the loader call are
 * syntax only the thing they mean can produce.
 */

const FONT_MODULE = join('lib', 'fonts', 'plus-jakarta-sans.ts');

function sources(dir: string): [string, string][] {
  return readdirSync(dir).flatMap((entry): [string, string][] => {
    if (entry === 'node_modules' || entry.startsWith('.') || entry === 'tests') return [];
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return sources(full);
    if (!/\.(tsx?|jsx?|mjs)$/.test(entry)) return [];
    return [[relative(WEB_ROOT, full), readFileSync(full, 'utf8')]];
  });
}

const SOURCES = ['app', 'components', 'config', 'i18n', 'lib'].flatMap((dir) =>
  sources(join(WEB_ROOT, dir)),
);

describe('self-hosted font', () => {
  it('nothing loads a font from Google Fonts', () => {
    const offenders = SOURCES.filter(([, source]) => /['"]next\/font\/google['"]/.test(source)).map(
      ([path]) => path,
    );
    expect(offenders).toEqual([]);
  });

  it('the face is defined in exactly one module', () => {
    const loaders = SOURCES.filter(([, source]) => /\blocalFont\s*\(/.test(source)).map(
      ([path]) => path,
    );
    expect(loaders).toEqual([FONT_MODULE]);
  });

  it('every document root takes its font from that module', () => {
    // Derived: any file rendering an `<html>` element is a root the face has to reach. Anchored to the
    // start of a line, so a comment that mentions the tag is not one.
    const roots = SOURCES.filter(([, source]) => /^\s*<html\b/m.test(source));
    console.info(`document roots: ${roots.map(([path]) => path).join(', ')}`);
    expect(roots.length).toBeGreaterThan(0);
    for (const [path, source] of roots) {
      expect(source, path).toMatch(/from '@\/lib\/fonts\/plus-jakarta-sans'/);
      expect(source, path).toMatch(/<html className=\{plusJakartaSans\.className\}/);
    }
  });

  it('the font file it loads is committed, with its licence beside it', () => {
    const source = readFileSync(join(WEB_ROOT, FONT_MODULE), 'utf8');
    const files = [...source.matchAll(/src:\s*'([^']+)'/g)].map((match) => match[1] ?? '');
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      expect(existsSync(join(WEB_ROOT, dirname(FONT_MODULE), file)), file).toBe(true);
    }
    expect(existsSync(join(WEB_ROOT, dirname(FONT_MODULE), 'OFL.txt'))).toBe(true);
  });
});
