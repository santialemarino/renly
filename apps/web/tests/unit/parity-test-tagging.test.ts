import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

/*
 * Every unit test that reads the API app's source is named `*.cross-app.test.ts(x)`, and only those are.
 *
 * The pre-commit hook scopes the suites to what is staged, and runs the cross-app files of BOTH apps on
 * every commit — they are the only web tests an API-only change can break. A parity test without the
 * suffix would silently drop out of that run, so the population is DERIVED from the test sources rather
 * than listed: a file counts as reading the API app when its code (comments stripped) builds a path into
 * it — a string naming the app's directory, or a `join` taking the parent segment and the app's name as
 * neighbouring arguments. The reverse holds too, so the suffix never drifts onto a file that would only
 * slow every commit down.
 */

const UNIT = __dirname;
const SELF = __filename;
const TAGGED = /\.cross-app\.test\.tsx?$/;
// `apps/api`, `../api`, `'apps', 'api'`, `'..', 'api'` — with the separator either a slash or a quoted
// argument boundary.
const READS_API = /(apps|\.\.)(\/|['"`]\s*,\s*['"`])api\b/;

function testFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return testFiles(full);
    return /\.test\.tsx?$/.test(entry) && full !== SELF ? [full] : [];
  });
}

// The source without block comments and `//` line comments (a `//` inside a URL is left alone).
function code(file: string): string {
  return readFileSync(file, 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|\s)\/\/.*$/gm, '$1');
}

const files = testFiles(UNIT).map((file) => ({
  name: relative(UNIT, file),
  reads: READS_API.test(code(file)),
  tagged: TAGGED.test(file),
}));

describe('cross-app test tagging', () => {
  // The derivation finds something, so a scanner that matches nothing cannot pass as "all tagged".
  it('derives a non-empty population of files reading the API source', () => {
    const readers = files.filter((f) => f.reads).map((f) => f.name);
    console.log('cross-app readers:', readers);
    expect(readers.length).toBeGreaterThan(0);
  });

  it('names every file that reads the API source *.cross-app.test.ts(x)', () => {
    expect(files.filter((f) => f.reads && !f.tagged).map((f) => f.name)).toEqual([]);
  });

  it('keeps the cross-app suffix off files that read no API source', () => {
    expect(files.filter((f) => f.tagged && !f.reads).map((f) => f.name)).toEqual([]);
  });
});
