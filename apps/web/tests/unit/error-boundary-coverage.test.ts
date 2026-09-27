import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/*
 * Every surface's failures land in a boundary drawn inside that surface's own chrome.
 *
 * The population is the route GROUPS under `app/`, found by listing the directory, so a fourth group
 * added later fails here until it has one. A group without its own `error.tsx` does not crash — its
 * errors fall through to `app/error.tsx` — which is exactly why nothing else would notice: the page
 * still renders a translated error, just without the header, footer or nav the visitor was using.
 *
 * Each boundary must render the shared `ErrorState` (so the copy, the retry that re-fetches server
 * data, and the testids are the same everywhere) and must report through `useReportBoundaryError`
 * (a caught error never reaches the browser SDK's global handler, so a boundary that forgets it
 * silently takes that surface's client errors out of Sentry). `app/error.tsx` and `app/global-error.tsx`
 * are held to the same, since they are the fallbacks behind every group.
 */

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, '..', '..', 'app');

const ROUTE_GROUPS = readdirSync(APP)
  .filter((entry) => /^\(.+\)$/.test(entry) && statSync(join(APP, entry)).isDirectory())
  .sort();

const BOUNDARIES = [
  ...ROUTE_GROUPS.map((group) => `${group}/error.tsx`),
  'error.tsx',
  'global-error.tsx',
];

describe('error boundary coverage', () => {
  it('derives every route group', () => {
    expect(ROUTE_GROUPS).toEqual(expect.arrayContaining(['(auth)', '(protected)', '(public)']));
  });

  it.each(BOUNDARIES)('app/%s exists, renders ErrorState and reports the error', (file) => {
    const path = join(APP, file);
    expect(existsSync(path), `app/${file} is missing`).toBe(true);

    const source = readFileSync(path, 'utf8');
    expect(source.startsWith("'use client';")).toBe(true);
    expect(source).toMatch(/<(ErrorState|GlobalErrorContent)\b/);
    expect(source).toMatch(/useReportBoundaryError\(error\);/);
  });
});
