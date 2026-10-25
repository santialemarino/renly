import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

/*
 * `@repo/ui/components` is ONE barrel that `export *`s every module, and the root layout imports it,
 * so every module in it — and every dependency those modules import — is in the client bundle of every
 * route. A dead `chart.tsx` in that barrel once shipped ~155 kB gz of recharts to 43 of 44 routes,
 * `/terms` and `/privacy` included. Three facts keep that from coming back, all derived from source:
 *
 *   * EVERY BARREL MODULE IS LIVE: at least one of its exports is imported by the web app from
 *     `@repo/ui/components`, or it is imported by another barrel module that is live. A module nothing
 *     reaches is dead code that still costs every route its dependencies.
 *   * NO BARREL MODULE IMPORTS `recharts`: charts render on a handful of pages and import recharts
 *     there, so it is split into those routes. Through the barrel it would ship everywhere again.
 *   * NO `dark:` UTILITY: the app has no dark mode (no `.dark` class, no dark tokens). A `dark:` class
 *     is dead, and with no custom variant declared Tailwind would apply it on an OS-level dark
 *     preference against light-only tokens.
 *
 * Imports are read with the TypeScript parser, so a comment or a string naming a component is not a
 * use of it. NOT covered: an export used only through a namespace import (`import * as UI`), which
 * the app does not do — such an import fails the first test loudly rather than passing it silently.
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');
const UI = join(WEB, '..', '..', 'packages', 'ui', 'src');
const BARREL = join(UI, 'components', 'index.ts');
const BARREL_SPECIFIER = '@repo/ui/components';
// The app's own source. Tests and build output are not the app.
const SKIPPED_DIRS = new Set([
  'node_modules',
  '.next',
  'tests',
  'public',
  'test-results',
  'playwright-report',
]);

// Lists every .ts/.tsx file under a directory, skipping the non-source dirs.
function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    if (SKIPPED_DIRS.has(name)) return [];
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.tsx?$/.test(name) && !name.endsWith('.d.ts') ? [path] : [];
  });
}

// Parses a file.
function parse(path: string): ts.SourceFile {
  return ts.createSourceFile(path, readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true);
}

// Every import declaration's specifier and the names it binds (the IMPORTED name, not an alias).
function imports(
  file: ts.SourceFile,
): { specifier: string; names: string[]; namespace: boolean }[] {
  return file.statements.filter(ts.isImportDeclaration).map((decl) => {
    const bindings = decl.importClause?.namedBindings;
    return {
      specifier: (decl.moduleSpecifier as ts.StringLiteral).text,
      names:
        bindings && ts.isNamedImports(bindings)
          ? bindings.elements.map((el) => (el.propertyName ?? el.name).text)
          : [],
      namespace: !!bindings && ts.isNamespaceImport(bindings),
    };
  });
}

// The names a module exports: exported declarations plus `export { … }` lists.
function exportedNames(file: ts.SourceFile): Set<string> {
  const names = new Set<string>();
  for (const stmt of file.statements) {
    if (ts.isExportDeclaration(stmt) && stmt.exportClause && ts.isNamedExports(stmt.exportClause)) {
      stmt.exportClause.elements.forEach((el) => names.add(el.name.text));
      continue;
    }
    const exported = ts.canHaveModifiers(stmt)
      ? ts.getModifiers(stmt)?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword)
      : false;
    if (!exported) continue;
    if (ts.isVariableStatement(stmt)) {
      stmt.declarationList.declarations.forEach(
        (d) => ts.isIdentifier(d.name) && names.add(d.name.text),
      );
    } else if (
      (ts.isFunctionDeclaration(stmt) ||
        ts.isClassDeclaration(stmt) ||
        ts.isInterfaceDeclaration(stmt) ||
        ts.isTypeAliasDeclaration(stmt) ||
        ts.isEnumDeclaration(stmt)) &&
      stmt.name
    ) {
      names.add(stmt.name.text);
    }
  }
  return names;
}

// The barrel's modules, as absolute paths, from its `export * from './x'` lines.
function barrelModules(): string[] {
  return parse(BARREL)
    .statements.filter(ts.isExportDeclaration)
    .map((decl) =>
      resolve(dirname(BARREL), `${(decl.moduleSpecifier as ts.StringLiteral).text}.tsx`),
    );
}

describe('the @repo/ui components barrel', () => {
  const modules = barrelModules();
  const webImports = sourceFiles(WEB).flatMap((path) =>
    imports(parse(path)).filter((imp) => imp.specifier === BARREL_SPECIFIER),
  );

  it('re-exports only modules the web app reaches', () => {
    expect(modules.length, 'the barrel lists no modules').toBeGreaterThan(10);
    expect(
      webImports.some((imp) => imp.namespace),
      'a namespace import of the barrel hides its uses',
    ).toBe(false);
    const usedNames = new Set(webImports.flatMap((imp) => imp.names));

    const live = new Set(
      modules.filter((path) => [...exportedNames(parse(path))].some((n) => usedNames.has(n))),
    );
    // A module a live module imports is live too (e.g. `button` under `pagination`).
    for (let grew = true; grew; ) {
      grew = false;
      for (const path of [...live]) {
        for (const imp of imports(parse(path))) {
          if (!imp.specifier.startsWith('.')) continue;
          const target = resolve(dirname(path), `${imp.specifier}.tsx`);
          if (modules.includes(target) && !live.has(target)) {
            live.add(target);
            grew = true;
          }
        }
      }
    }

    const dead = modules.filter((path) => !live.has(path)).map((path) => relative(UI, path));
    expect(dead, 'barrel modules nothing in apps/web reaches — delete them').toEqual([]);
  });

  it('never imports recharts, so charts stay split into the routes that render one', () => {
    const offenders = sourceFiles(UI)
      .filter((path) => imports(parse(path)).some((imp) => imp.specifier === 'recharts'))
      .map((path) => relative(UI, path));
    expect(offenders).toEqual([]);
  });
});

describe('dark mode', () => {
  it('has no dark: utilities, because the app has no dark mode', () => {
    const files = [...sourceFiles(WEB), ...sourceFiles(UI)];
    expect(files.length).toBeGreaterThan(100);
    const offenders = files.filter((path) =>
      /(?<![\w-])dark:[\w[-]/.test(readFileSync(path, 'utf8')),
    );
    expect(offenders.map((path) => relative(join(WEB, '..', '..'), path))).toEqual([]);
  });
});
