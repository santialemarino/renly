import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

/*
 * Every money figure the app RENDERS goes through `MoneyFigure`, which is what puts `data-money` on it
 * — and the e2e overflow sweep can only find the figures that carry it. A figure rendered raw is one
 * the sweep cannot see, so a regression that clips it would pass the sweep in silence. This is the
 * guard that keeps the marker from quietly thinning out.
 *
 * It reads the source through the TypeScript parser rather than a regex, because the shapes a figure
 * is rendered in are syntax a regex cannot tell apart: `{fmt.value(x)}` as a JSX child is a figure,
 * `{cond ? fmt.value(x) : '—'}` is too, and so is a template carrying the currency code — while
 * `t('owed', { amount: fmt.value(x) })` is a figure inside a SENTENCE, which wraps with its sentence
 * and is not what this is about, and a Recharts `formatter` callback is a tooltip string.
 *
 * A call counts as rendered when, walking out from it through only the expressions that pass a value
 * through unchanged (parentheses, a ternary branch, `&&`/`||`/`??`, a template), it lands in a JSX
 * expression — as an element's child or as an attribute's value. It is then allowed only as the child
 * of a `MoneyFigure`. The receiver is whatever the file bound to `useFormatters()` / `getFormatters()`,
 * so renaming `fmt` does not switch the guard off.
 *
 * What it cannot see, stated rather than implied: a figure formatted into a variable first and
 * rendered from that variable, and one passed as a string prop to a component that renders it (the
 * pot header's stat list, the wizards' `format` callbacks). Those render as wrapping text in rows
 * that grow with it; the metric cards, tables and legends the sweep exists for do not use either.
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');

const MONEY_METHODS = new Set(['value', 'amount', 'signedValue']);
const FORMATTER_FACTORIES = new Set(['useFormatters', 'getFormatters']);

// The expressions a value passes through unchanged on its way into JSX.
function passesThrough(node: ts.Node): boolean {
  return (
    ts.isParenthesizedExpression(node) ||
    ts.isConditionalExpression(node) ||
    ts.isBinaryExpression(node) ||
    ts.isTemplateSpan(node) ||
    ts.isTemplateExpression(node) ||
    ts.isAsExpression(node) ||
    ts.isNonNullExpression(node)
  );
}

// The names this file bound to the formatter set: `const fmt = useFormatters()`, or
// `const fmt = await getFormatters()`.
function formatterNames(file: ts.SourceFile): Set<string> {
  const names = new Set<string>();
  const visit = (node: ts.Node) => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
      const init = ts.isAwaitExpression(node.initializer)
        ? node.initializer.expression
        : node.initializer;
      if (
        ts.isCallExpression(init) &&
        ts.isIdentifier(init.expression) &&
        FORMATTER_FACTORIES.has(init.expression.text)
      )
        names.add(node.name.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return names;
}

interface MoneyCall {
  line: number;
  text: string;
  rendered: boolean;
  wrapped: boolean;
}

// Every money-formatting call in the source, and whether it is rendered and whether it is wrapped.
function moneyCalls(source: string, fileName = 'file.tsx'): MoneyCall[] {
  const file = ts.createSourceFile(
    fileName,
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const receivers = formatterNames(file);
  const calls: MoneyCall[] = [];
  const visit = (node: ts.Node) => {
    if (
      ts.isCallExpression(node) &&
      ts.isPropertyAccessExpression(node.expression) &&
      ts.isIdentifier(node.expression.expression) &&
      receivers.has(node.expression.expression.text) &&
      MONEY_METHODS.has(node.expression.name.text)
    ) {
      let outer: ts.Node = node.parent;
      while (passesThrough(outer)) outer = outer.parent;
      const rendered = ts.isJsxExpression(outer);
      const owner = rendered ? outer.parent : undefined;
      const wrapped =
        owner !== undefined &&
        ts.isJsxElement(owner) &&
        owner.openingElement.tagName.getText(file) === 'MoneyFigure';
      calls.push({
        line: file.getLineAndCharacterOfPosition(node.getStart(file)).line + 1,
        text: node.getText(file).split('\n')[0] ?? '',
        rendered,
        wrapped,
      });
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return calls;
}

function readTsx(dir: string): [string, string][] {
  const out: [string, string][] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry.startsWith('.')) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...readTsx(full));
    else if (entry.endsWith('.tsx')) out.push([relative(WEB, full), readFileSync(full, 'utf8')]);
  }
  return out;
}

const SOURCES = [...readTsx(join(WEB, 'app')), ...readTsx(join(WEB, 'components'))];

describe('the scanner itself', () => {
  // The fixtures each guard shape by shape, so a scanner that stopped recognising one reads red here
  // rather than green on the real tree.
  const hook = `const fmt = useFormatters();\n`;

  it('flags a figure rendered raw, in every shape a figure is rendered in', () => {
    const shapes = [
      '<p>{fmt.value(total)}</p>',
      "<p>{total ? fmt.amount(total, 'ARS') : '—'}</p>",
      '<p>{shown && fmt.signedValue(change)}</p>',
      '<p>{`${fmt.amount(total, code)} ${code}`}</p>',
      '<Row value={fmt.value(total)} />',
      '<ul>{rows.map((row) => <li key={row.id}>{fmt.value(row.total)}</li>)}</ul>',
    ];
    shapes.forEach((jsx) => {
      const calls = moneyCalls(`${hook}const el = ${jsx};`);
      expect(calls, jsx).toHaveLength(1);
      expect(calls[0], jsx).toMatchObject({ rendered: true, wrapped: false });
    });
  });

  it('accepts a figure wrapped in MoneyFigure, in the same shapes', () => {
    const shapes = [
      '<MoneyFigure>{fmt.value(total)}</MoneyFigure>',
      "<p>{total ? <MoneyFigure>{fmt.amount(total, 'ARS')}</MoneyFigure> : '—'}</p>",
      '<MoneyFigure>{`${fmt.amount(total, code)} ${code}`}</MoneyFigure>',
      '<Row value={<MoneyFigure>{fmt.value(total)}</MoneyFigure>} />',
    ];
    shapes.forEach((jsx) => {
      const calls = moneyCalls(`${hook}const el = ${jsx};`);
      expect(calls, jsx).toHaveLength(1);
      expect(calls[0], jsx).toMatchObject({ rendered: true, wrapped: true });
    });
  });

  it('leaves a figure inside a sentence or a callback alone', () => {
    const shapes = [
      "<p>{t('owed', { amount: fmt.amount(total, code) })}</p>",
      '<Tooltip formatter={(v) => fmt.value(Number(v), { compact: true })} />',
      'toast(fmt.value(total))',
    ];
    shapes.forEach((expr) => {
      const calls = moneyCalls(`${hook}const el = ${expr};`);
      expect(calls, expr).toHaveLength(1);
      expect(calls[0]?.rendered, expr).toBe(false);
    });
  });

  it('follows the receiver to whatever name the file bound it to', () => {
    const calls = moneyCalls(
      'const money = await getFormatters();\nconst el = <p>{money.value(1)}</p>;',
    );
    expect(calls).toMatchObject([{ rendered: true, wrapped: false }]);
    // And a same-named method on something that is NOT the formatter set is not money.
    expect(moneyCalls('const el = <p>{field.value(1)}</p>;')).toHaveLength(0);
  });
});

describe('money figures in the app', () => {
  const all = SOURCES.flatMap(([path, source]) =>
    moneyCalls(source, path).map((call) => ({ path, ...call })),
  );

  it('are all rendered through MoneyFigure', () => {
    const raw = all
      .filter((call) => call.rendered && !call.wrapped)
      .map((call) => `${call.path}:${call.line}  ${call.text}`);
    expect(raw).toEqual([]);
  });

  it('are found at all — the scan is reading the tree it claims to', () => {
    // A floor well under today's forty-odd rather than a count, so adding or removing a figure never
    // trips it: its job is only to catch a scan that silently matched nothing (a moved directory, a
    // renamed factory), which would pass the assertion above with an empty list.
    expect(all.filter((call) => call.wrapped).length).toBeGreaterThan(20);
  });
});
