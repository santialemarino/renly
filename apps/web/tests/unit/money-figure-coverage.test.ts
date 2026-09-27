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
 * A money call is followed OUT of the expression it sits in, through everything that hands its value
 * on unchanged, to where the value ends up:
 *   * pass-throughs: parentheses, a ternary's branches (not its condition), the value side of `&&` /
 *     `||` / `??`, a template, `String(...)`, `as` / `!`;
 *   * a callback's result: an arrow whose body is the value, when the arrow is a `.map(...)` argument
 *     (followed on from the `.map` call) or a column's `cell` renderer;
 *   * a variable: every reference to it in the scope that declares it is followed in turn;
 *   * display data: an object property named `value` or `cell`, which is how the app's stat lists,
 *     sample tables and detail dialogs carry what they then render.
 * It counts as rendered when it ends in a JSX expression (an element's child, or an attribute) or in
 * display data, and is allowed only as the direct child of a `MoneyFigure`. The receiver is whatever
 * the file bound to `useFormatters()` / `getFormatters()` — by name, or destructured
 * (`const { amount } = useFormatters()`), so renaming `fmt` does not switch the guard off.
 *
 * A second check reads the other direction: a currency code rendered as the SIBLING right after a
 * `MoneyFigure` sits outside the marked box, so a clipped code would pass the sweep. The code goes
 * inside.
 *
 * What it still cannot see, stated rather than implied: a figure handed to a function or component as
 * an argument or a prop other than `value` / `cell` (the shared wizards' `format` callbacks), a
 * variable exported or passed out of the scope that declares it, and a formatter set that is not
 * obtained from the two factories (passed in as a prop).
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');

const MONEY_METHODS = new Set(['value', 'amount', 'signedValue']);
const FORMATTER_FACTORIES = new Set(['useFormatters', 'getFormatters']);
const DISPLAY_PROPERTIES = new Set(['value', 'cell']);
const LOGICAL = new Set([
  ts.SyntaxKind.AmpersandAmpersandToken,
  ts.SyntaxKind.BarBarToken,
  ts.SyntaxKind.QuestionQuestionToken,
]);

type Landing = 'wrapped' | 'raw' | 'none';

interface Receivers {
  // Names bound to the whole formatter set (`fmt`).
  sets: Set<string>;
  // Names bound to one money method by destructuring (`amount`, or `v` for `{ value: v }`).
  methods: Set<string>;
}

// What this file bound to the formatter set, by name and by destructuring.
function receiversOf(file: ts.SourceFile): Receivers {
  const receivers: Receivers = { sets: new Set(), methods: new Set() };
  const visit = (node: ts.Node) => {
    if (ts.isVariableDeclaration(node) && node.initializer) {
      const init = ts.isAwaitExpression(node.initializer)
        ? node.initializer.expression
        : node.initializer;
      if (
        ts.isCallExpression(init) &&
        ts.isIdentifier(init.expression) &&
        FORMATTER_FACTORIES.has(init.expression.text)
      ) {
        if (ts.isIdentifier(node.name)) receivers.sets.add(node.name.text);
        if (ts.isObjectBindingPattern(node.name)) {
          node.name.elements.forEach((element) => {
            const method = (element.propertyName ?? element.name).getText(file);
            if (MONEY_METHODS.has(method) && ts.isIdentifier(element.name))
              receivers.methods.add(element.name.text);
          });
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return receivers;
}

function isMoneyCall(node: ts.Node, receivers: Receivers): node is ts.CallExpression {
  if (!ts.isCallExpression(node)) return false;
  const callee = node.expression;
  if (ts.isIdentifier(callee)) return receivers.methods.has(callee.text);
  return (
    ts.isPropertyAccessExpression(callee) &&
    ts.isIdentifier(callee.expression) &&
    receivers.sets.has(callee.expression.text) &&
    MONEY_METHODS.has(callee.name.text)
  );
}

// The node that receives `node`'s value unchanged, or undefined when `node` is consumed there.
function passedTo(node: ts.Node): ts.Node | undefined {
  const parent = node.parent;
  if (
    ts.isParenthesizedExpression(parent) ||
    ts.isAsExpression(parent) ||
    ts.isNonNullExpression(parent) ||
    ts.isTemplateSpan(parent) ||
    ts.isTemplateExpression(parent)
  )
    return parent;
  if (ts.isConditionalExpression(parent) && parent.condition !== node) return parent;
  if (ts.isBinaryExpression(parent) && LOGICAL.has(parent.operatorToken.kind)) return parent;
  if (
    ts.isCallExpression(parent) &&
    ts.isIdentifier(parent.expression) &&
    parent.expression.text === 'String' &&
    parent.arguments.includes(node as ts.Expression)
  )
    return parent;
  return undefined;
}

// The scope a variable is visible in: the nearest enclosing block or file.
function scopeOf(node: ts.Node): ts.Node {
  let scope = node.parent;
  while (!ts.isBlock(scope) && !ts.isSourceFile(scope)) scope = scope.parent;
  return scope;
}

function combine(landings: Landing[]): Landing {
  if (landings.includes('raw')) return 'raw';
  if (landings.includes('wrapped')) return 'wrapped';
  return 'none';
}

// Where the value of `start` ends up.
function landing(start: ts.Node, file: ts.SourceFile, depth = 0): Landing {
  if (depth > 8) return 'none';
  let node = start;
  for (let next = passedTo(node); next; next = passedTo(node)) node = next;
  const parent = node.parent;

  if (ts.isJsxExpression(parent)) {
    if (ts.isJsxAttribute(parent.parent)) return 'raw';
    const owner = parent.parent;
    return ts.isJsxElement(owner) && owner.openingElement.tagName.getText(file) === 'MoneyFigure'
      ? 'wrapped'
      : 'raw';
  }
  if (ts.isPropertyAssignment(parent) && parent.initializer === node) {
    return DISPLAY_PROPERTIES.has(parent.name.getText(file)) ? 'raw' : 'none';
  }
  if (ts.isArrowFunction(parent) && parent.body === node) {
    const holder = parent.parent;
    if (ts.isPropertyAssignment(holder) && holder.name.getText(file) === 'cell') return 'raw';
    if (
      ts.isCallExpression(holder) &&
      ts.isPropertyAccessExpression(holder.expression) &&
      holder.expression.name.text === 'map'
    )
      return landing(holder, file, depth + 1);
    return 'none';
  }
  if (
    ts.isVariableDeclaration(parent) &&
    parent.initializer === node &&
    ts.isIdentifier(parent.name)
  ) {
    const name = parent.name.text;
    const declared = parent.name;
    const references: ts.Node[] = [];
    const visit = (child: ts.Node) => {
      if (
        ts.isIdentifier(child) &&
        child.text === name &&
        child !== declared &&
        !(ts.isPropertyAccessExpression(child.parent) && child.parent.name === child) &&
        !(ts.isPropertyAssignment(child.parent) && child.parent.name === child)
      )
        references.push(child);
      ts.forEachChild(child, visit);
    };
    visit(scopeOf(parent));
    return combine(references.map((reference) => landing(reference, file, depth + 1)));
  }
  return 'none';
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
  const receivers = receiversOf(file);
  const calls: MoneyCall[] = [];
  const visit = (node: ts.Node) => {
    if (isMoneyCall(node, receivers)) {
      const where = landing(node, file);
      calls.push({
        line: file.getLineAndCharacterOfPosition(node.getStart(file)).line + 1,
        text: node.getText(file).split('\n')[0] ?? '',
        rendered: where !== 'none',
        wrapped: where === 'wrapped',
      });
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return calls;
}

// Whether an expression renders a currency code and nothing else: a `.currency` field, a variable
// named for one (`currency`, `currencySuffix`), or either behind a ternary or a template that adds
// nothing but spacing. Deliberately narrow — a sibling SENTENCE that merely mentions `x.currency`
// among its arguments is copy, not a code beside a figure.
function isCodeExpression(expr: ts.Expression): boolean {
  if (ts.isParenthesizedExpression(expr)) return isCodeExpression(expr.expression);
  if (ts.isPropertyAccessExpression(expr)) return expr.name.text === 'currency';
  if (ts.isIdentifier(expr)) return /currency/i.test(expr.text);
  if (ts.isConditionalExpression(expr)) {
    const blank = (e: ts.Expression) =>
      ts.isStringLiteral(e) || e.kind === ts.SyntaxKind.NullKeyword;
    return (
      (isCodeExpression(expr.whenTrue) && blank(expr.whenFalse)) ||
      (isCodeExpression(expr.whenFalse) && blank(expr.whenTrue))
    );
  }
  if (ts.isTemplateExpression(expr))
    return (
      expr.head.text.trim() === '' &&
      expr.templateSpans.every(
        (span) => span.literal.text.trim() === '' && isCodeExpression(span.expression),
      )
    );
  return false;
}

// Whether a JSX child renders a currency code and nothing else, directly or as an element's only child.
function isCodeChild(child: ts.JsxChild): boolean {
  if (ts.isJsxExpression(child)) return !!child.expression && isCodeExpression(child.expression);
  if (ts.isJsxElement(child)) {
    const inner = child.children.filter((c) => !(ts.isJsxText(c) && c.text.trim() === ''));
    return inner.length === 1 && isCodeChild(inner[0] as ts.JsxChild);
  }
  return false;
}

// Every `MoneyFigure` whose next rendered sibling is a currency code — i.e. a code outside the marker.
function codesBesideFigures(source: string, fileName = 'file.tsx'): string[] {
  const file = ts.createSourceFile(
    fileName,
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const found: string[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isJsxElement(node) && node.openingElement.tagName.getText(file) === 'MoneyFigure') {
      const parent = node.parent;
      if (ts.isJsxElement(parent) || ts.isJsxFragment(parent)) {
        const siblings = parent.children;
        const after = siblings.slice(siblings.indexOf(node) + 1).find((sibling) => {
          if (ts.isJsxText(sibling)) return sibling.text.trim() !== '';
          // `{' '}` and `{/* comments */}` render nothing a reader sees as a neighbour.
          if (ts.isJsxExpression(sibling))
            return !!sibling.expression && !ts.isStringLiteral(sibling.expression);
          return true;
        });
        if (after && isCodeChild(after)) {
          const line = file.getLineAndCharacterOfPosition(after.getStart(file)).line + 1;
          found.push(`${line}  ${after.getText(file).replace(/\s+/g, ' ').slice(0, 80)}`);
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return found;
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
      '<p>{String(fmt.amount(total, code))}</p>',
      '<Row value={fmt.value(total)} />',
      '<ul>{rows.map((row) => <li key={row.id}>{fmt.value(row.total)}</li>)}</ul>',
      '<p>{rows.map((row) => fmt.amount(row.total, code))}</p>',
      "[{ header: 'Amount', cell: (row) => fmt.amount(row.amount, row.currency) }]",
      "[{ label: 'Value', value: pot.nav === null ? '—' : fmt.amount(pot.nav, code) }]",
    ];
    shapes.forEach((jsx) => {
      const calls = moneyCalls(`${hook}const el = ${jsx};`);
      expect(calls, jsx).toHaveLength(1);
      expect(calls[0], jsx).toMatchObject({ rendered: true, wrapped: false });
    });
  });

  it('follows a figure through a variable to where it is rendered', () => {
    const raw = moneyCalls(`${hook}const shown = fmt.value(total);\nconst el = <p>{shown}</p>;`);
    expect(raw).toMatchObject([{ rendered: true, wrapped: false }]);
    const wrapped = moneyCalls(
      `${hook}const shown = fmt.value(total);\nconst el = shown ? <MoneyFigure>{shown}</MoneyFigure> : null;`,
    );
    expect(wrapped).toMatchObject([{ rendered: true, wrapped: true }]);
  });

  it('follows a destructured formatter', () => {
    const calls = moneyCalls(
      'const { amount, value: v } = useFormatters();\nconst el = <p>{amount(total, code)}{v(1)}</p>;',
    );
    expect(calls).toMatchObject([
      { rendered: true, wrapped: false },
      { rendered: true, wrapped: false },
    ]);
  });

  it('accepts a figure wrapped in MoneyFigure, in the same shapes', () => {
    const shapes = [
      '<MoneyFigure>{fmt.value(total)}</MoneyFigure>',
      "<p>{total ? <MoneyFigure>{fmt.amount(total, 'ARS')}</MoneyFigure> : '—'}</p>",
      '<MoneyFigure>{`${fmt.amount(total, code)} ${code}`}</MoneyFigure>',
      '<Row value={<MoneyFigure>{fmt.value(total)}</MoneyFigure>} />',
      "[{ cell: (row) => <MoneyFigure>{fmt.amount(row.amount, 'ARS')}</MoneyFigure> }]",
    ];
    shapes.forEach((jsx) => {
      const calls = moneyCalls(`${hook}const el = ${jsx};`);
      expect(calls, jsx).toHaveLength(1);
      expect(calls[0], jsx).toMatchObject({ rendered: true, wrapped: true });
    });
  });

  it('leaves a figure inside a sentence, a callback or a condition alone', () => {
    const shapes = [
      "<p>{t('owed', { amount: fmt.amount(total, code) })}</p>",
      '<Tooltip formatter={(v) => fmt.value(Number(v), { compact: true })} />',
      'toast(fmt.value(total))',
      "<p>{fmt.value(total) === '0' ? 'none' : 'some'}</p>",
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

  it('finds a currency code rendered beside the figure instead of inside it', () => {
    const outside = [
      "<p><MoneyFigure>{fmt.amount(a, c)}</MoneyFigure>{' '}<span>{account.currency}</span></p>",
      '<p><MoneyFigure>{fmt.amount(a, c)}</MoneyFigure>{currencySuffix}</p>',
      "<p><MoneyFigure>{fmt.amount(a, c)}</MoneyFigure> {o.converted ? '' : o.currency}</p>",
    ];
    outside.forEach((jsx) => expect(codesBesideFigures(`const el = ${jsx};`), jsx).toHaveLength(1));
    const inside = [
      "<p><MoneyFigure>{fmt.amount(a, c)}{' '}<span>{account.currency}</span></MoneyFigure></p>",
      '<p><MoneyFigure>{fmt.amount(a, c)}</MoneyFigure><span>{t("per month")}</span></p>',
    ];
    inside.forEach((jsx) => expect(codesBesideFigures(`const el = ${jsx};`), jsx).toEqual([]));
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

  it('carry their currency code inside the marker, never beside it', () => {
    const beside = SOURCES.flatMap(([path, source]) =>
      codesBesideFigures(source, path).map((found) => `${path}:${found}`),
    );
    expect(beside).toEqual([]);
  });

  it('are found at all — the scan is reading the tree it claims to', () => {
    // A floor well under today's fifty-odd rather than a count, so adding or removing a figure never
    // trips it: its job is only to catch a scan that silently matched nothing (a moved directory, a
    // renamed factory), which would pass the assertion above with an empty list.
    expect(all.filter((call) => call.wrapped).length).toBeGreaterThan(20);
  });
});
