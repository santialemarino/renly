import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

import { WEB_ROOT } from '../e2e/helpers/list-pages';

/*
 * Every donut draws its slices with the one shared stroke, `DONUT_STROKE_WIDTH`. Recharts' default is a
 * white 1px outline round each slice, so a donut that leaves it out reads as a different chart from the
 * others; the dashboard's composition donut did, beside the two distribution donuts that set it. Read
 * from source: every `<Pie` element, wherever it is drawn.
 */

function sources(dir: string): [string, string][] {
  return readdirSync(dir).flatMap((entry): [string, string][] => {
    if (entry === 'node_modules' || entry.startsWith('.')) return [];
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return sources(full);
    if (!entry.endsWith('.tsx')) return [];
    return [[relative(WEB_ROOT, full), readFileSync(full, 'utf8')]];
  });
}

describe('donut stroke', () => {
  it('every Pie sets the shared stroke width', () => {
    const pies = ['app', 'components'].flatMap((dir) =>
      sources(join(WEB_ROOT, dir)).flatMap(([path, source]) =>
        [...source.matchAll(/<Pie\b[^>]*>/g)].map((match): [string, string] => [path, match[0]]),
      ),
    );
    console.info(`pies: ${pies.map(([path]) => path).join(', ')}`);
    expect(pies.length).toBeGreaterThan(0);
    for (const [path, pie] of pies) {
      expect(pie, path).toMatch(/strokeWidth=\{DONUT_STROKE_WIDTH\}/);
    }
  });
});
