import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

import { WEB_ROOT } from '../e2e/helpers/list-pages';

/*
 * `truncate` on a flex container draws no ellipsis: its text sits in anonymous flex items, which clip
 * at the container's edge with nothing to say they were cut. A label that may run long truncates in a
 * block of its own (a flex ITEM is blockified, so `truncate` there does draw the ellipsis), through
 * `TruncatingTooltip` where the whole text has to stay readable. Comboboxes and dialogs sit outside the
 * e2e text sweep's reach, which is how eight of them shipped the bug, so this reads every class list in
 * the web app's source instead.
 */

const CLASS_LIST = /(['"`])([^'"`\n]*\btruncate\b[^'"`\n]*)\1/g;

function sources(dir: string): [string, string][] {
  return readdirSync(dir).flatMap((entry): [string, string][] => {
    if (entry === 'node_modules' || entry.startsWith('.')) return [];
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return sources(full);
    if (!entry.endsWith('.tsx')) return [];
    return [[relative(WEB_ROOT, full), readFileSync(full, 'utf8')]];
  });
}

describe('truncate on a flex container', () => {
  it('no class list makes the same element both flex and truncate', () => {
    const lists = ['app', 'components'].flatMap((dir) =>
      sources(join(WEB_ROOT, dir)).flatMap(([path, source]) =>
        [...source.matchAll(CLASS_LIST)].map((match): [string, string] => [path, match[2] ?? '']),
      ),
    );
    console.info(`class lists with truncate: ${lists.length}`);
    expect(lists.length).toBeGreaterThan(0);
    const offenders = lists
      .filter(([, list]) =>
        list.split(/\s+/).some((cls) => cls === 'flex' || cls === 'inline-flex'),
      )
      .map(([path, list]) => `${path}: ${list}`);
    expect(offenders).toEqual([]);
  });
});
