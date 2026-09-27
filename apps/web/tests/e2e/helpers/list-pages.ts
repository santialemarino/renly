import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

/*
 * The app's LIST pages, derived from source rather than listed: a page is a list page when its
 * `searchParams` declares a `search` param — that param is what the list toolbar's search box writes,
 * so a page that reads it is a page with a toolbar to hit-test. Shared by the e2e toolbar sweep and
 * the unit guard that holds every one of these pages to `EntityListToolbar`, so the two cannot
 * disagree about which pages exist.
 */

export const WEB_ROOT = join(import.meta.dirname, '..', '..', '..');
const APP_ROOT = join(WEB_ROOT, 'app');

// The declaration only a page reading the param can produce: `search?: string` in its props type.
export const SEARCH_PARAM_DECLARATION = /\bsearch\?\s*:\s*string\b/;

export interface ListPage {
  // Path of the page.tsx, relative to apps/web.
  file: string;
  // The URL it serves, with route groups dropped.
  route: string;
}

function pageFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return pageFiles(full);
    return entry === 'page.tsx' ? [full] : [];
  });
}

export function listPages(): ListPage[] {
  return pageFiles(APP_ROOT)
    .filter((file) => SEARCH_PARAM_DECLARATION.test(readFileSync(file, 'utf8')))
    .map((file) => {
      const segments = relative(APP_ROOT, file).split(sep).slice(0, -1);
      /*
       * A dynamic segment has no URL to visit without an id, and a sweep that silently skipped it
       * would report a page it never looked at as clean — so it fails instead, naming the page.
       */
      const dynamic = segments.find((segment) => segment.startsWith('['));
      if (dynamic) throw new Error(`list page under a dynamic segment needs an id: ${file}`);
      const route = segments.filter((segment) => !/^\(.*\)$/.test(segment)).join('/');
      return { file: relative(WEB_ROOT, file), route: `/${route}` };
    });
}
