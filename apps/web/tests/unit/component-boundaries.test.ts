import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

/*
 * Two structural rules about components, held by reading every `.tsx` under `app/` and `components/`
 * with the TypeScript parser.
 *
 * NAMED PROPS. A component's props are a named `<Component>Props` type declared right above it, never
 * an object literal written into the parameter (`({ a }: { a: string })`). A component is a function
 * (declaration, arrow or function expression) with a PascalCase name; a lower-case helper that happens
 * to destructure an object is not one. `Readonly<{ … }>` and an intersection holding a literal count as
 * inline too.
 *
 * NO NEEDLESS CLIENT BOUNDARY. A `'use client'` file must use something only the client has — otherwise
 * it ships its code to the browser and turns a server-rendered subtree into a hydrated one for nothing.
 * Deciding "server-safe" for certain needs types, so this check only FLAGS a file when every one of the
 * following is absent, and treats anything it cannot prove inert as a client feature:
 *
 *   * a hook call (`use…(` or `use(`), except `useTranslations`, whose server twin is `getTranslations`
 *     — and only in a file no client file imports, since an async server component cannot render
 *     under a client parent;
 *   * a browser global (`window`, `document`, timers, observers, storage, …);
 *   * an event handler or `ref` attribute (a bare boolean `onLoad` is a prop, not a handler);
 *   * a function value written in the file anywhere but as a call's argument (a `.map` callback is fine;
 *     an arrow in an attribute, an object or a variable may reach a client child as a prop);
 *   * a spread attribute, or a function/component-typed prop passed on as an attribute value (a
 *     `LucideIcon` prop rendered as `<Icon />` here is fine; one handed to a child is not);
 *   * an import from a package other than the inert ones in `INERT_PACKAGES`, or from an app module or
 *     `@repo/ui` component that has no `'use client'` of its own but calls a hook (rendering it from a
 *     server component would run that hook on the server).
 *
 * False-positive policy: a flagged file has none of the above, so removing its directive (and swapping
 * `useTranslations` for `getTranslations` in an async component) is safe; `next build` confirms it. A
 * file that must stay a boundary for a reason this cannot see goes in `CLIENT_BOUNDARY_EXCEPTIONS` with
 * that reason. False negatives are accepted: anything unproven counts as client, so a file that could
 * be a server component but passes, say, a computed value of an unknown kind is not flagged.
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');
const UI_COMPONENTS = join(WEB, '..', '..', 'packages', 'ui', 'src', 'components');
const SCANNED_DIRS = ['app', 'components'];

// Packages whose imports cannot make a component client-only by themselves.
const INERT_PACKAGES = new Set(['lucide-react', 'next/link', 'next-intl', '@repo/ui/lib', 'react']);
const BROWSER_GLOBALS = new Set([
  'window',
  'document',
  'navigator',
  'localStorage',
  'sessionStorage',
  'history',
  'location',
  'matchMedia',
  'requestAnimationFrame',
  'setTimeout',
  'setInterval',
  'IntersectionObserver',
  'ResizeObserver',
  'MutationObserver',
]);
// A component-typed prop: rendering it here is fine, handing it to a child crosses the boundary.
const COMPONENT_TYPE = /(Icon|ComponentType|ElementType|FC)$/;

// Files that stay `'use client'` though nothing above marks them, and why.
const CLIENT_BOUNDARY_EXCEPTIONS: Record<string, string> = {};

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return entry.startsWith('.') ? [] : sourceFiles(full);
    return entry.endsWith('.tsx') ? [full] : [];
  });
}

const parsed = new Map<string, ts.SourceFile>();
function parse(path: string): ts.SourceFile {
  let file = parsed.get(path);
  if (!file) {
    file = ts.createSourceFile(path, readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true);
    parsed.set(path, file);
  }
  return file;
}

function isUseClient(file: ts.SourceFile): boolean {
  const first = file.statements[0];
  return (
    !!first &&
    ts.isExpressionStatement(first) &&
    ts.isStringLiteral(first.expression) &&
    first.expression.text === 'use client'
  );
}

function walk(node: ts.Node, visit: (node: ts.Node) => void) {
  visit(node);
  ts.forEachChild(node, (child) => walk(child, visit));
}

function isHookCall(node: ts.Node, allowTranslations: boolean): boolean {
  if (!ts.isCallExpression(node) || !ts.isIdentifier(node.expression)) return false;
  const name = node.expression.text;
  if (allowTranslations && name === 'useTranslations') return false;
  return name === 'use' || /^use[A-Z]/.test(name);
}

// A module with no directive that still calls a hook: it only works when a client file imports it.
function hookingWithoutDirective(path: string): boolean {
  const file = parse(path);
  if (isUseClient(file)) return false;
  let found = false;
  walk(file, (node) => {
    if (isHookCall(node, false)) found = true;
  });
  return found;
}

function resolveAppModule(specifier: string): string | undefined {
  const base = join(WEB, specifier.slice(2));
  return ['.tsx', '.ts', '/index.tsx', '/index.ts']
    .map((suffix) => base + suffix)
    .find((path) => existsSync(path));
}

// Which `@repo/ui` source file declares each name the barrel exports.
const uiExports = (() => {
  const byName = new Map<string, string>();
  const barrel = parse(join(UI_COMPONENTS, 'index.ts'));
  barrel.statements.forEach((statement) => {
    if (!ts.isExportDeclaration(statement) || !statement.moduleSpecifier) return;
    const spec = (statement.moduleSpecifier as ts.StringLiteral).text;
    const path = ['.tsx', '.ts']
      .map((suffix) => join(UI_COMPONENTS, spec + suffix))
      .find((p) => existsSync(p));
    if (!path) return;
    walk(parse(path), (node) => {
      if (ts.isExportSpecifier(node)) byName.set(node.name.text, path);
      if (
        (ts.isFunctionDeclaration(node) || ts.isVariableStatement(node)) &&
        node.modifiers?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword)
      ) {
        const names = ts.isFunctionDeclaration(node)
          ? [node.name?.text]
          : node.declarationList.declarations.map((d) => d.name.getText());
        names.forEach((name) => name && byName.set(name, path));
      }
    });
  });
  return byName;
})();

// Every reason the file needs the client; empty means nothing marks it.
function clientFeatures(path: string): string[] {
  const file = parse(path);
  const reasons: string[] = [];
  const passedOnProps = new Set<string>();

  file.statements.forEach((statement) => {
    if (!ts.isImportDeclaration(statement) || statement.importClause?.isTypeOnly) return;
    const spec = (statement.moduleSpecifier as ts.StringLiteral).text;
    const named = statement.importClause?.namedBindings;
    const valueNames =
      named && ts.isNamedImports(named)
        ? named.elements.filter((e) => !e.isTypeOnly).map((e) => (e.propertyName ?? e.name).text)
        : [];
    if (spec.startsWith('@/')) {
      const target = resolveAppModule(spec);
      if (target && hookingWithoutDirective(target))
        reasons.push(`imports ${spec}, which calls a hook`);
    } else if (spec === '@repo/ui/components') {
      valueNames.forEach((name) => {
        const target = uiExports.get(name);
        if (target && hookingWithoutDirective(target))
          reasons.push(`renders ${name}, which calls a hook`);
      });
    } else if (!INERT_PACKAGES.has(spec)) {
      reasons.push(`imports ${spec}`);
    }
  });

  // Props typed as a function or a component, by their local binding name.
  walk(file, (node) => {
    if (!(ts.isInterfaceDeclaration(node) || ts.isTypeLiteralNode(node))) return;
    node.members.forEach((member) => {
      if (!ts.isPropertySignature(member) || !member.type || !ts.isIdentifier(member.name)) return;
      const type = member.type;
      if (
        ts.isFunctionTypeNode(type) ||
        (ts.isTypeReferenceNode(type) && COMPONENT_TYPE.test(type.typeName.getText()))
      ) {
        passedOnProps.add(member.name.text);
      }
    });
  });
  walk(file, (node) => {
    if (ts.isBindingElement(node) && ts.isIdentifier(node.name)) {
      const prop =
        node.propertyName && ts.isIdentifier(node.propertyName)
          ? node.propertyName.text
          : node.name.text;
      if (passedOnProps.has(prop)) passedOnProps.add(node.name.text);
    }
  });

  walk(file, (node) => {
    if (isHookCall(node, true))
      reasons.push(`calls ${(node as ts.CallExpression).expression.getText()}`);
    if (
      ts.isIdentifier(node) &&
      BROWSER_GLOBALS.has(node.text) &&
      !(ts.isPropertyAccessExpression(node.parent) && node.parent.name === node) &&
      !ts.isPropertyAssignment(node.parent) &&
      !ts.isPropertySignature(node.parent)
    ) {
      reasons.push(`uses ${node.text}`);
    }
    if (ts.isJsxSpreadAttribute(node)) reasons.push('spreads attributes');
    if (ts.isJsxAttribute(node)) {
      const name = node.name.getText();
      const value = node.initializer;
      const literalTrue =
        !value ||
        (ts.isJsxExpression(value) && value.expression?.kind === ts.SyntaxKind.TrueKeyword);
      if ((/^on[A-Z]/.test(name) && !literalTrue) || name === 'ref') reasons.push(`sets ${name}`);
      if (value && ts.isJsxExpression(value) && value.expression) {
        walk(value.expression, (inner) => {
          if (ts.isIdentifier(inner) && passedOnProps.has(inner.text))
            reasons.push(`passes ${inner.text} on`);
        });
      }
    }
    if (
      (ts.isArrowFunction(node) || ts.isFunctionExpression(node)) &&
      !ts.isCallExpression(node.parent) &&
      !(
        ts.isVariableDeclaration(node.parent) &&
        ts.isVariableStatement(node.parent.parent.parent) &&
        node.parent.parent.parent.parent === file
      )
    ) {
      reasons.push('writes a function value');
    }
  });
  return reasons;
}

// PascalCase functions whose first parameter is typed inline, as `path: Name`.
function inlinePropsTypes(path: string): string[] {
  const file = parse(path);
  const found: string[] = [];
  const isInline = (type: ts.TypeNode | undefined): boolean =>
    !!type &&
    (ts.isTypeLiteralNode(type) ||
      (ts.isTypeReferenceNode(type) &&
        type.typeName.getText() === 'Readonly' &&
        isInline(type.typeArguments?.[0])) ||
      (ts.isIntersectionTypeNode(type) && type.types.some(isInline)) ||
      (ts.isParenthesizedTypeNode(type) && isInline(type.type)));
  walk(file, (node) => {
    let name: string | undefined;
    let fn: ts.SignatureDeclaration | undefined;
    if (ts.isFunctionDeclaration(node) && node.name) {
      name = node.name.text;
      fn = node;
    } else if (
      ts.isVariableDeclaration(node) &&
      ts.isIdentifier(node.name) &&
      node.initializer &&
      (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer))
    ) {
      name = node.name.text;
      fn = node.initializer;
    }
    if (name && fn && /^[A-Z]/.test(name) && isInline(fn.parameters[0]?.type)) found.push(name);
  });
  return found;
}

const FILES = SCANNED_DIRS.flatMap((dir) => sourceFiles(join(WEB, dir)));
const rel = (path: string) => relative(WEB, path);

describe('component boundaries', () => {
  it('scans the components', () => {
    console.info(`component-boundaries: ${FILES.length} .tsx files scanned`);
    expect(FILES.length).toBeGreaterThan(200);
  });

  it('declares every component props type as a named type, never inline', () => {
    const offenders = FILES.flatMap((path) =>
      inlinePropsTypes(path).map((name) => `${rel(path)}: ${name}`),
    );
    expect(
      offenders,
      'move the literal into a `<Component>Props` type right above the component',
    ).toEqual([]);
  });

  it("marks a file 'use client' only when something in it needs the client", () => {
    const clientFiles = FILES.filter((path) => isUseClient(parse(path)));
    console.info(`component-boundaries: ${clientFiles.length} 'use client' files checked`);
    expect(clientFiles.length).toBeGreaterThan(100);
    // A component a client file renders cannot become an async server component, so one that only
    // calls `useTranslations` stays a client component when any client file imports it.
    const importedByClient = new Set(
      clientFiles.flatMap((path) =>
        parse(path)
          .statements.filter(ts.isImportDeclaration)
          .map((statement) => (statement.moduleSpecifier as ts.StringLiteral).text)
          .filter((spec) => spec.startsWith('@/'))
          .map((spec) => resolveAppModule(spec))
          .filter((target): target is string => !!target),
      ),
    );
    const needless = clientFiles
      .filter((path) => !(rel(path) in CLIENT_BOUNDARY_EXCEPTIONS))
      .filter((path) => clientFeatures(path).length === 0)
      .filter(
        (path) => !(importedByClient.has(path) && /\buseTranslations\(/.test(parse(path).text)),
      )
      .map(rel);
    expect(
      needless,
      "nothing here needs the client: drop 'use client' (useTranslations → await getTranslations)",
    ).toEqual([]);
  });

  it('lists only exceptions that still exist and are still client boundaries', () => {
    Object.keys(CLIENT_BOUNDARY_EXCEPTIONS).forEach((path) => {
      expect(existsSync(join(WEB, path)), path).toBe(true);
      expect(isUseClient(parse(join(WEB, path))), path).toBe(true);
    });
  });
});
