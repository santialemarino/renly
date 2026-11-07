import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/*
 * Status colours come from the semantic tokens (`text-success`, `bg-warning-subtle`, `text-gain`,
 * `bg-danger-solid`, the `--chart-*` marks…), never from a raw palette shade.
 *
 * The tokens are written once, in `packages/ui/src/styles/index.css`, at shades measured against every
 * surface they land on. A raw `text-amber-500` or `text-red-500` beside them is how the app once
 * carried a 2.15:1 caution figure and two different reds for one meaning, and a render only shows that
 * on the page somebody opens with the data that triggers it. So this reads the source text instead:
 * every `.ts`, `.tsx` and `.css` under `apps/web/{app,components,lib}` and `packages/ui/src`, and
 * refuses three spellings of a status hue anywhere but the token file:
 *
 *   1. a palette utility (`text-emerald-600`, `hover:bg-red-50/50`, `ring-amber-500/40`…), in any string,
 *      template or cva map, under any variant prefix;
 *   2. a colour literal whose hue is a status hue: `oklch(…)` by its own hue angle, `#hex` / `rgb(…)` by
 *      its HSL hue (blue brand values and greys pass);
 *   3. a reference to a palette variable (`var(--color-red-500)`, `text-(--color-red-500)`).
 *
 * Brand blue and the neutrals are other systems and are not policed here.
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');
const REPO = join(WEB, '..', '..');
const TOKEN_FILE = join('packages', 'ui', 'src', 'styles', 'index.css');

const STATUS_HUES = 'red|rose|orange|amber|yellow|lime|green|emerald|teal';

function readSources(root: string): [string, string][] {
  const out: [string, string][] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      if (entry === 'node_modules' || entry === 'tests' || entry.startsWith('.')) continue;
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (/\.(tsx?|css)$/.test(entry))
        out.push([relative(REPO, full), readFileSync(full, 'utf8')]);
    }
  };
  walk(root);
  return out;
}

const SOURCES = [
  ...readSources(join(WEB, 'app')),
  ...readSources(join(WEB, 'components')),
  ...readSources(join(WEB, 'lib')),
  ...readSources(join(REPO, 'packages', 'ui', 'src')),
];
const POLICED = SOURCES.filter(([path]) => path !== TOKEN_FILE);

// Every match of `pattern` in `source` that `keep` accepts, as `path:line text`.
function offenders(
  path: string,
  source: string,
  pattern: RegExp,
  keep: (match: RegExpMatchArray) => boolean = () => true,
): string[] {
  return [...source.matchAll(pattern)]
    .filter(keep)
    .map((match) => `${path}:${source.slice(0, match.index).split('\n').length} ${match[0]}`);
}

// A palette utility naming a status hue, under any chain of variant prefixes, with an optional alpha.
const PALETTE_CLASS = new RegExp(
  `(?<![\\w-])(?:[\\w\\-\\[\\]&/.:=()'"]+:)*(?:text|bg|border(?:-[trblxyse])?|ring|ring-offset|fill|stroke|outline|decoration|divide|from|via|to|shadow|accent|caret|placeholder)-(?:${STATUS_HUES})-\\d{2,3}(?:\\/\\d+)?(?![\\w-])`,
  'g',
);
const PALETTE_VARIABLE = new RegExp(`--color-(?:${STATUS_HUES})-\\d{2,3}\\b`, 'g');
const OKLCH = /oklch\(\s*([\d.]+%?)\s+([\d.]+)\s+([\d.]+)/g;
// A hex colour where a colour goes (a string, an arbitrary value, a CSS declaration), so an issue
// reference in prose (`#170`) is not one.
const HEX = /(?<=['"`[(,]|:\s?)#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})(?![\w-])/g;
const RGB = /rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/g;

// oklch hue angles of the status families (red through teal) and of rose; a near-grey has no hue.
function isStatusOklch([, , chroma, hue]: RegExpMatchArray): boolean {
  const h = Number(hue);
  return Number(chroma) > 0.03 && (h < 200 || h >= 340);
}

// The HSL hue of an sRGB colour: red/orange/amber/yellow/lime/green/emerald/teal sit below 185°,
// rose above 330°; blue and violet fall between, and an unsaturated grey has no hue at all.
function isStatusRgb(r: number, g: number, b: number): boolean {
  const [max, min] = [Math.max(r, g, b), Math.min(r, g, b)];
  const lightness = (max + min) / 2 / 255;
  const delta = (max - min) / 255;
  if (delta === 0) return false;
  const saturation = delta / (1 - Math.abs(2 * lightness - 1));
  if (saturation < 0.2) return false;
  let hue =
    max === r
      ? ((g - b) / (max - min)) % 6
      : max === g
        ? (b - r) / (max - min) + 2
        : (r - g) / (max - min) + 4;
  hue = (hue * 60 + 360) % 360;
  return hue < 185 || hue >= 330;
}

function hexIsStatus([hex]: RegExpMatchArray): boolean {
  const digits = hex.slice(1);
  const full = digits.length === 3 ? [...digits].map((d) => d + d).join('') : digits;
  const channel = (i: number) => parseInt(full.slice(i, i + 2), 16);
  return isStatusRgb(channel(0), channel(2), channel(4));
}

function rgbIsStatus([, r, g, b]: RegExpMatchArray): boolean {
  return isStatusRgb(Number(r), Number(g), Number(b));
}

describe('status colours come from the semantic tokens', () => {
  it('walks the sources, the token file among them', () => {
    console.log(`status-colour guard: ${POLICED.length} source files policed`);
    expect(SOURCES.length).toBeGreaterThan(150);
    expect(SOURCES.some(([path]) => path === TOKEN_FILE)).toBe(true);
    expect(SOURCES.some(([path]) => path.includes(join('apps', 'web', 'app')))).toBe(true);
  });

  it('uses no palette utility of a status hue', () => {
    const found = POLICED.flatMap(([path, source]) => offenders(path, source, PALETTE_CLASS));
    expect(found).toEqual([]);
  });

  it('writes no status-hue colour literal outside the token file', () => {
    const found = POLICED.flatMap(([path, source]) => [
      ...offenders(path, source, OKLCH, isStatusOklch),
      ...offenders(path, source, HEX, hexIsStatus),
      ...offenders(path, source, RGB, rgbIsStatus),
    ]);
    expect(found).toEqual([]);
  });

  it('references no status-hue palette variable', () => {
    const found = POLICED.flatMap(([path, source]) => offenders(path, source, PALETTE_VARIABLE));
    expect(found).toEqual([]);
  });

  /*
   * The detectors themselves, on fixtures: a vacuous regex would pass the three checks above on any
   * tree. Each status spelling must be caught and each neighbouring legal one must pass.
   */
  it('catches every status spelling and passes the legal neighbours', () => {
    const caught = (source: string) =>
      [
        ...offenders('x', source, PALETTE_CLASS),
        ...offenders('x', source, PALETTE_VARIABLE),
        ...offenders('x', source, OKLCH, isStatusOklch),
        ...offenders('x', source, HEX, hexIsStatus),
        ...offenders('x', source, RGB, rgbIsStatus),
      ].length > 0;
    for (const bad of [
      `'text-red-500'`,
      `"flex hover:bg-emerald-50/50 p-2"`,
      `cva('x', { variants: { tone: { bad: 'border-amber-200' } } })`,
      'group-hover/row:text-green-700',
      `'data-[state=on]:ring-orange-400/40'`,
      `'border-t-rose-300'`,
      `fill: 'oklch(0.6 0.2 25)'`,
      `color: '#dc2626'`,
      `color: '#0a0'`,
      `'#900'`,
      'color: #f59e0b;',
      'box-shadow: 0 0 0 1px rgba(220, 38, 38, 0.5)',
      'background: var(--color-red-500)',
      `'text-(--color-emerald-600)'`,
      `'text-[oklch(0.555_0.163_48.998)]'`.replace(/_/g, ' '),
    ])
      expect(caught(bad), bad).toBe(true);
    for (const good of [
      `'text-danger bg-success-subtle border-warning-border'`,
      `'text-gain hover:text-loss bg-danger-solid'`,
      `'text-blue-700 bg-neutral-50 ring-blue-800/50'`,
      `'text-redacted'`,
      `fill: 'oklch(0.424 0.199 265.638)'`,
      `'oklch(0.97 0 0)'`,
      `color: '#1e40af'`,
      `color: '#48505e'`,
      'rgb(0 0 0 / 0.18)',
      `href="#faded"`,
      '// removed in #170, see #235',
      'var(--color-blue-800)',
    ])
      expect(caught(good), good).toBe(false);
  });
});
