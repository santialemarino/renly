import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

/*
 * Every form that WRITES a currency offers only the set the API accepts. The API rejects anything
 * outside the exchange-rate-supported set with a 422, so a picker offering the full ISO list lets a
 * user choose a value that can only fail on save. The restriction is `CurrencyCombobox`'s `codes`
 * prop, fed from `getSupportedCurrencies()` on the page and handed down through every component in
 * between — and it failed both ways before this guard: two entry dialogs never set `codes`, and three
 * more set nothing to pass it.
 *
 * Two checks, each over a population derived from the source:
 *   * every `<CurrencyCombobox>` sets `codes`, except the display and preference pickers below, which
 *     keep the full list on purpose (a display currency without a rate falls back, it never fails);
 *   * every component whose `<Name>Props` declares `supportedCurrencies` receives it at EVERY render,
 *     so the list cannot stop one hop short of the picker that reads it.
 *
 * What it cannot see: whether the value handed down is the real list (a caller passing `undefined`
 * explicitly reads as passed), and a picker rendered under another name.
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');
const ROOTS = ['app', 'components'];

// Pickers that keep the full ISO list, with why. Keyed by file, since a file's pickers share a role.
const FULL_LIST_PICKERS: Record<string, string> = {
  'app/(protected)/preferences/_components/preferences-form.tsx':
    'primary and preferred display currencies — display only, never written to an entry',
};

// Renders that legitimately omit `supportedCurrencies`, with why. Keyed by `file → component`.
const UNFED_RENDERS: Record<string, string> = {
  'app/(protected)/shared/pots/[id]/_components/pot-header.tsx → PotFormDialog':
    'edit mode only, which hides the currency field: a pot keeps the base currency it was created with',
};

interface JsxUse {
  file: string;
  tag: string;
  // The file that declares the rendered component: the render's own file for a local component,
  // otherwise the module it is imported from. Two files may declare unrelated components of one name.
  declaredIn: string | undefined;
  line: number;
  attributes: Set<string>;
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === 'node_modules' ? [] : sourceFiles(path);
    return path.endsWith('.tsx') ? [path] : [];
  });
}

const files = ROOTS.flatMap((root) => sourceFiles(join(WEB, root))).map((path) => ({
  file: relative(WEB, path),
  source: ts.createSourceFile(path, readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true),
}));

const uses: JsxUse[] = [];
// `file → Name` for every `<Name>Props` interface declaring `supportedCurrencies`.
const fedComponents = new Set<string>();

// Where each name a file renders is declared: locally, or the `@/…` module it imports it from.
function declarations(file: string, source: ts.SourceFile): Map<string, string> {
  const declared = new Map<string, string>();
  for (const statement of source.statements) {
    if (ts.isFunctionDeclaration(statement) && statement.name)
      declared.set(statement.name.text, file);
    if (
      ts.isImportDeclaration(statement) &&
      ts.isStringLiteral(statement.moduleSpecifier) &&
      statement.moduleSpecifier.text.startsWith('@/') &&
      statement.importClause?.namedBindings &&
      ts.isNamedImports(statement.importClause.namedBindings)
    ) {
      const importedFrom = `${statement.moduleSpecifier.text.slice(2)}.tsx`;
      for (const element of statement.importClause.namedBindings.elements) {
        declared.set(element.name.text, importedFrom);
      }
    }
  }
  return declared;
}

for (const { file, source } of files) {
  const declared = declarations(file, source);
  const visit = (node: ts.Node) => {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tag = node.tagName.getText(source);
      uses.push({
        file,
        tag,
        declaredIn: declared.get(tag),
        line: source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1,
        attributes: new Set(
          node.attributes.properties
            .filter(ts.isJsxAttribute)
            .map((attribute) => attribute.name.getText(source)),
        ),
      });
    }
    if (
      ts.isInterfaceDeclaration(node) &&
      node.name.text.endsWith('Props') &&
      node.members.some((member) => member.name?.getText(source) === 'supportedCurrencies')
    ) {
      fedComponents.add(`${file} → ${node.name.text.slice(0, -'Props'.length)}`);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
}

describe('currency pickers that write offer only the supported set', () => {
  const pickers = uses.filter((use) => use.tag === 'CurrencyCombobox');

  it('finds the pickers', () => {
    expect(pickers.length).toBeGreaterThan(10);
  });

  it('every writing picker sets `codes`', () => {
    const unrestricted = pickers
      .filter((use) => !use.attributes.has('codes') && !(use.file in FULL_LIST_PICKERS))
      .map((use) => `${use.file}:${use.line}`);
    expect(unrestricted).toEqual([]);
  });

  it('every full-list exception still renders a picker', () => {
    for (const file of Object.keys(FULL_LIST_PICKERS)) {
      expect(pickers.some((use) => use.file === file && !use.attributes.has('codes'))).toBe(true);
    }
  });
});

describe('`supportedCurrencies` reaches every render of a component that declares it', () => {
  it('finds the components, each declared beside its own function', () => {
    expect(fedComponents.size).toBeGreaterThan(20);
    for (const key of fedComponents) {
      const [file, component] = key.split(' → ');
      const declared = files.find((entry) => entry.file === file)!.source.getText();
      expect(declared, `${component}Props has no ${component} in ${file}`).toMatch(
        new RegExp(`function ${component}\\b`),
      );
    }
  });

  it('resolves where the rendered components are declared', () => {
    const resolved = uses.filter((use) => fedComponents.has(`${use.declaredIn} → ${use.tag}`));
    expect(resolved.length).toBeGreaterThan(30);
  });

  it('every render passes it', () => {
    const unfed = uses
      .filter((use) => fedComponents.has(`${use.declaredIn} → ${use.tag}`))
      .filter((use) => !use.attributes.has('supportedCurrencies'))
      .filter((use) => !(`${use.file} → ${use.tag}` in UNFED_RENDERS))
      .map((use) => `${use.file}:${use.line} <${use.tag}>`);
    expect(unfed).toEqual([]);
  });

  it('every unfed exception is still a real render', () => {
    for (const key of Object.keys(UNFED_RENDERS)) {
      const [file, tag] = key.split(' → ');
      expect(uses.some((use) => use.file === file && use.tag === tag)).toBe(true);
    }
  });
});
