import { readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/*
 * No signed-in page has a route loading state.
 *
 * A navigation keeps the old page on screen until the new one is complete and then swaps it in at once;
 * the click itself is answered by the sidebar and, past a short wait, by the progress bar and the dimmed
 * page (`NavigationPending`). A `loading.tsx` breaks that: Next mounts it the moment a navigation
 * starts — blanking `<main>` or showing a placeholder — and once mounted React keeps it for ~300 ms
 * however soon the page is ready, so every click got slower and showed an empty or stand-in page. What
 * makes a page fast is starting its reads early (`page-read-rounds.test.ts`), not a placeholder.
 *
 * The population is every directory a protected page renders under: `app/` itself (a root boundary
 * wraps every group) and the whole `app/(protected)` tree, walked rather than listed so a route added
 * tomorrow is covered. Any `loading.*` there fails.
 */

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, '..', '..', 'app');
const PROTECTED = join(APP, '(protected)');
const LOADING_FILE = /^loading\.(tsx|ts|jsx|js)$/;

// Every directory under `dir`, itself included, relative to `app/`.
function directoriesUnder(dir: string): string[] {
  const out = [relative(APP, dir) || '.'];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...directoriesUnder(full));
  }
  return out;
}

const SCANNED = ['.', ...directoriesUnder(PROTECTED)];

describe('route loading states', () => {
  it('scans app/ and every directory of the protected tree', () => {
    // The walk found the protected sections and their nested routes, not an empty or moved tree.
    expect(SCANNED).toContain('(protected)/dashboard');
    expect(SCANNED).toContain('(protected)/shared/pots/[id]/buy-out');
    expect(SCANNED.length).toBeGreaterThan(40);
  });

  it('exist nowhere a protected page renders', () => {
    const found = SCANNED.flatMap((dir) =>
      readdirSync(join(APP, dir))
        .filter((entry) => LOADING_FILE.test(entry))
        .map((entry) => join(dir, entry)),
    );
    expect(
      found,
      'a route loading state blanks the page on every navigation to it and holds it ~300 ms — ' +
        'start the page reads earlier instead',
    ).toEqual([]);
  });
});
