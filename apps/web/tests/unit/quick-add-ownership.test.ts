import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

/*
 * The quick-add's forms must be owned OUTSIDE the sidebar — a structural fact, held here by reading the
 * source with the TypeScript parser.
 *
 * Below `md` the sidebar is a Sheet, a closed Sheet is unmounted, and opening a quick-add form closes
 * it (it would otherwise sit behind the dialog with its own overlay). So a form owned anywhere in the
 * sidebar's tree is unmounted with the Sheet — which is exactly how the quick-add shipped: on a phone
 * the form appeared and was gone about 300ms later. Nothing but a browser at a phone width can SEE
 * that, and the e2e spec does; this is the guard that fails in the editor, before anyone opens one.
 *
 * Both sides are derived, never listed:
 *
 *   * THE SIDEBAR TREE is every module reachable, through static imports, re-exports and `import()`,
 *     from any module that renders the base `<Sidebar>` from `@repo/ui` — the component that becomes
 *     the Sheet. `import()` counts: a dynamically loaded form rendered by a sidebar module is inside
 *     the Sheet all the same.
 *   * THE FORMS are the entry forms (every module rendering `<EntryTypeField>`, the control that only
 *     an entry form carries), plus every module their OWNER loads with `import()` — which adds the
 *     linked-plan mismatch prompt, a dialog the owner opens after a form closes and so the one most
 *     exposed to a closed Sheet.
 *
 * JSX is matched as parsed opening tags, never by grepping names: a comment, a string or a closing tag
 * that mentions `ExpenseFormDialog` is not a render of it, and a regex cannot tell them apart. A tag
 * is resolved through the file's own imports, so an aliased import (`ExpenseFormDialog as Form`) is
 * still the form, and "inside a sidebar component" covers JSX passed in a PROP as well as in children
 * (`<AppSidebar footer={<ExpenseFormDialog />} />`).
 *
 * NOT covered, stated rather than implied: a form handed over as a component VALUE rather than as
 * JSX (`<AppSidebar dialog={ExpenseFormDialog} />`, or via a variable), since nothing in the element
 * tree names it — the e2e spec at a phone width is what catches that.
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');
// Everything the app is built from. The tests and build output are not, and a dependency is never
// followed — only app-local specifiers are.
const SKIPPED_DIRS = new Set(['node_modules', 'tests', 'public']);
const RESOLVE_SUFFIXES = ['.tsx', '.ts', '/index.tsx', '/index.ts'];

// The base component that renders as a Sheet below `md`, and where it comes from.
const SHEET_COMPONENT = 'Sidebar';
const UI_COMPONENTS = '@repo/ui/components';
// The control only an entry form renders — the expense/income toggle at the top of all four.
const ENTRY_FORM_MARKER = 'EntryTypeField';
// The attribute the trigger carries; the e2e specs click it by the same id.
const TRIGGER_TEST_ID = 'quick-add-trigger';

interface Module {
  path: string;
  // Every module specifier: `import … from`, `export … from`, and `import('…')`.
  specifiers: string[];
  // Only the `import('…')` ones.
  dynamicSpecifiers: string[];
  // Local names bound by a named import, keyed by the LOCAL name (an alias, when there is one).
  namedImports: Map<string, { specifier: string; imported: string }>;
  exports: string[];
  // Every JSX element, as its tag name plus the tag names of every element nested inside it.
  elements: { tag: string; descendants: string[] }[];
  testIds: string[];
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      return SKIPPED_DIRS.has(entry) || entry.startsWith('.') ? [] : sourceFiles(full);
    }
    return /\.tsx?$/.test(entry) && !entry.endsWith('.d.ts') ? [full] : [];
  });
}

function tagName(node: ts.JsxOpeningElement | ts.JsxSelfClosingElement): string {
  return node.tagName.getText();
}

function parse(path: string): Module {
  const source = ts.createSourceFile(
    path,
    readFileSync(path, 'utf8'),
    ts.ScriptTarget.Latest,
    true,
    path.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const mod: Module = {
    path,
    specifiers: [],
    dynamicSpecifiers: [],
    namedImports: new Map(),
    exports: [],
    elements: [],
    testIds: [],
  };

  // The tag names of every JSX element at or below `node`.
  const tagsWithin = (node: ts.Node): string[] => {
    const found: string[] = [];
    const walk = (child: ts.Node) => {
      if (ts.isJsxOpeningElement(child) || ts.isJsxSelfClosingElement(child)) {
        found.push(tagName(child));
      }
      ts.forEachChild(child, walk);
    };
    ts.forEachChild(node, walk);
    return found;
  };

  const visit = (node: ts.Node) => {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      const specifier = node.moduleSpecifier.text;
      mod.specifiers.push(specifier);
      const bindings = node.importClause?.namedBindings;
      if (bindings && ts.isNamedImports(bindings)) {
        bindings.elements.forEach((element) =>
          mod.namedImports.set(element.name.text, {
            specifier,
            imported: (element.propertyName ?? element.name).text,
          }),
        );
      }
    }
    if (
      ts.isExportDeclaration(node) &&
      node.moduleSpecifier &&
      ts.isStringLiteral(node.moduleSpecifier)
    ) {
      mod.specifiers.push(node.moduleSpecifier.text);
    }
    if (
      ts.isCallExpression(node) &&
      node.expression.kind === ts.SyntaxKind.ImportKeyword &&
      node.arguments[0] &&
      ts.isStringLiteral(node.arguments[0])
    ) {
      mod.specifiers.push(node.arguments[0].text);
      mod.dynamicSpecifiers.push(node.arguments[0].text);
    }
    const exported = ts
      .getModifiers(node as ts.HasModifiers)
      ?.some((modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword);
    if (exported && ts.isFunctionDeclaration(node) && node.name) mod.exports.push(node.name.text);
    if (exported && ts.isVariableStatement(node)) {
      node.declarationList.declarations.forEach((declaration) => {
        if (ts.isIdentifier(declaration.name)) mod.exports.push(declaration.name.text);
      });
    }
    if (ts.isJsxElement(node)) {
      mod.elements.push({ tag: tagName(node.openingElement), descendants: tagsWithin(node) });
    }
    if (ts.isJsxSelfClosingElement(node)) {
      // Its descendants are whatever JSX its attributes carry — a form passed in a prop.
      mod.elements.push({ tag: tagName(node), descendants: tagsWithin(node) });
    }
    if (
      ts.isJsxAttribute(node) &&
      node.name.getText() === 'data-testid' &&
      node.initializer &&
      ts.isStringLiteral(node.initializer)
    ) {
      mod.testIds.push(node.initializer.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return mod;
}

// The file an app-local specifier names, or null for a package, a JSON file, or anything outside.
function resolveSpecifier(from: string, specifier: string): string | null {
  let base: string;
  if (specifier.startsWith('@/')) base = join(WEB, specifier.slice(2));
  else if (specifier.startsWith('.')) base = resolve(dirname(from), specifier);
  else return null;
  const hit = RESOLVE_SUFFIXES.map((suffix) => base + suffix).find((path) => existsSync(path));
  return hit ?? null;
}

const MODULES = new Map(sourceFiles(WEB).map((path) => [path, parse(path)] as const));
const rel = (path: string) => relative(WEB, path);

const rendersTag = (mod: Module, tag: string) => mod.elements.some((el) => el.tag === tag);

// Every module reachable from `roots` through any import edge, the roots included.
function closure(roots: string[]): Set<string> {
  const seen = new Set<string>();
  const queue = [...roots];
  while (queue.length > 0) {
    const path = queue.pop()!;
    if (seen.has(path)) continue;
    seen.add(path);
    const mod = MODULES.get(path);
    mod?.specifiers
      .map((specifier) => resolveSpecifier(path, specifier))
      .forEach((next) => next && !seen.has(next) && queue.push(next));
  }
  return seen;
}

// The file a tag's component comes from, when the module imports it from an app-local path.
function tagSource(mod: Module, tag: string): string | null {
  const binding = mod.namedImports.get(tag);
  return binding ? resolveSpecifier(mod.path, binding.specifier) : null;
}

// Whether `tag`, in `mod`, is the base Sheet-capable `<Sidebar>` from @repo/ui, under any local name.
function isSheetTag(mod: Module, tag: string): boolean {
  const binding = mod.namedImports.get(tag);
  return binding?.specifier === UI_COMPONENTS && binding.imported === SHEET_COMPONENT;
}

const SIDEBAR_ROOTS = [...MODULES.values()]
  .filter((mod) => mod.elements.some((el) => isSheetTag(mod, el.tag)))
  .map((mod) => mod.path);
const SIDEBAR_TREE = closure(SIDEBAR_ROOTS);

const ENTRY_FORMS = [...MODULES.values()]
  .filter((mod) => rendersTag(mod, ENTRY_FORM_MARKER))
  .map((mod) => mod.path);

// Whoever loads an entry form on demand: the quick-add's owner.
const OWNERS = [...MODULES.values()]
  .filter((mod) =>
    mod.dynamicSpecifiers.some((specifier) =>
      ENTRY_FORMS.includes(resolveSpecifier(mod.path, specifier) ?? ''),
    ),
  )
  .map((mod) => mod.path);

const OWNED_DIALOGS = [
  ...new Set([
    ...ENTRY_FORMS,
    ...OWNERS.flatMap((owner) =>
      MODULES.get(owner)!
        .dynamicSpecifiers.map((specifier) => resolveSpecifier(owner, specifier))
        .filter((path): path is string => path !== null),
    ),
  ]),
];
// The component names those modules export — what a render of one of them has to spell as its tag.
const OWNED_DIALOG_NAMES = new Set(OWNED_DIALOGS.flatMap((path) => MODULES.get(path)!.exports));

// Whether `tag`, in `mod`, renders an owned dialog: imported from one under any local name, or spelled
// with one's exported name.
function isOwnedDialogTag(mod: Module, tag: string): boolean {
  return OWNED_DIALOGS.includes(tagSource(mod, tag) ?? '') || OWNED_DIALOG_NAMES.has(tag);
}

describe('the quick-add forms are owned outside the sidebar', () => {
  it('derives a population worth checking', () => {
    // Guards on the guard: each derivation returning nothing would make every assertion below pass
    // empty — the vacuous shape this file exists to avoid.
    expect(SIDEBAR_ROOTS.map(rel)).toEqual([
      join('app', '(protected)', '_components', 'sidebar.tsx'),
    ]);
    expect(SIDEBAR_TREE.size).toBeGreaterThan(5);
    // The four canonical entry forms the web-components-pages skill names, at least.
    expect(ENTRY_FORMS.length).toBeGreaterThanOrEqual(4);
    expect(OWNERS.length).toBeGreaterThanOrEqual(1);
    // The owner loads something beyond the entry forms (the mismatch prompt), so the second half of
    // the population is real rather than a restatement of the first.
    expect(OWNED_DIALOGS.length).toBeGreaterThan(ENTRY_FORMS.length);
    expect(OWNED_DIALOG_NAMES.size).toBeGreaterThanOrEqual(OWNED_DIALOGS.length);
  });

  it('keeps the trigger in the sidebar', () => {
    // The other half of the split: were the trigger to leave the sidebar, the tree below could be
    // empty of forms for the trivial reason that the quick-add is gone from it altogether.
    // RENDERED there, not merely imported: an import left behind after the element was deleted would
    // still put the module in the tree.
    const carriers = [...MODULES.values()].filter((mod) => mod.testIds.includes(TRIGGER_TEST_ID));
    expect(carriers.map((mod) => rel(mod.path))).toHaveLength(1);
    const triggerNames = new Set(carriers.flatMap((mod) => mod.exports));
    const renderedBy = [...SIDEBAR_TREE].filter((path) =>
      (MODULES.get(path)?.elements ?? []).some((el) => triggerNames.has(el.tag)),
    );
    expect(renderedBy.map(rel)).toEqual([join('app', '(protected)', '_components', 'sidebar.tsx')]);
  });

  it('reaches no owned dialog, and no module that loads one, from the sidebar', () => {
    const reached = [...SIDEBAR_TREE].filter(
      (path) => OWNED_DIALOGS.includes(path) || OWNERS.includes(path),
    );
    expect(reached.map(rel)).toEqual([]);
  });

  it('renders no owned dialog in any sidebar module', () => {
    const offenders = [...SIDEBAR_TREE].flatMap((path) =>
      (MODULES.get(path)?.elements ?? [])
        .filter((el) => isOwnedDialogTag(MODULES.get(path)!, el.tag))
        .map((el) => `${rel(path)}: <${el.tag}>`),
    );
    expect(offenders).toEqual([]);
  });

  it('passes no owned dialog INTO the sidebar as a child', () => {
    // A module outside the tree can still put a form inside the Sheet by nesting it under a sidebar
    // component — the import walk above cannot see that, the element tree can.
    const sidebarExports = new Set(
      [...SIDEBAR_TREE].flatMap((path) => MODULES.get(path)?.exports ?? []),
    );
    const isSidebarTag = (mod: Module, tag: string) =>
      isSheetTag(mod, tag) ||
      SIDEBAR_TREE.has(tagSource(mod, tag) ?? '') ||
      sidebarExports.has(tag);
    const offenders = [...MODULES.values()].flatMap((mod) =>
      mod.elements
        .filter((el) => isSidebarTag(mod, el.tag))
        .flatMap((el) => el.descendants.filter((tag) => isOwnedDialogTag(mod, tag)))
        .map((tag) => `${rel(mod.path)}: <${tag}> inside a sidebar component`),
    );
    expect(offenders).toEqual([]);
  });

  it('has the owner rendered by the protected layout, around the sidebar', () => {
    const layout = MODULES.get(join(WEB, 'app', '(protected)', 'layout.tsx'))!;
    const ownerExports = new Set(OWNERS.flatMap((path) => MODULES.get(path)!.exports));
    const sidebarExports = new Set(SIDEBAR_ROOTS.flatMap((path) => MODULES.get(path)!.exports));
    // Around it, because the trigger reads the owner through context: rendered beside it instead, the
    // trigger would throw on its first render.
    const wrapping = layout.elements.filter(
      (el) => ownerExports.has(el.tag) && el.descendants.some((tag) => sidebarExports.has(tag)),
    );
    expect(wrapping.length).toBe(1);
  });
});
