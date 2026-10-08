import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/*
 * `skipped_currencies` is an API field that only does its job if the WEB reads it, and nothing in
 * either language could see that it was being dropped.
 *
 * The API computes the codes correctly and has done since Phase 3 — there are unit tests for that. The
 * web's raw interface simply did not declare the field, so TypeScript never complained (a missing
 * optional property is not an error on an interface the code never asks for), the mapper dropped it,
 * and the page had nothing to render. The result on /finance-dashboard was a total that had silently
 * left rows out: income read 1,000.00 where the figure was 1,974.53, with nothing on screen to say so.
 * /payments-calendar had the same gap.
 *
 * ▸ WHY A TEXT SCAN, which is usually the weak kind of test. The invariant is that two files in two
 * languages agree, and there is no runtime moment where both exist: the API module is Python, the web
 * module is `server-only` and cannot even be imported into this suite. A type-level check cannot help
 * either — the defect WAS the type. So the honest guard reads both sides as text and asserts the
 * correspondence, and the anti-vacuity test below is what keeps that from degenerating.
 *
 * ▸ WHAT IT DOES NOT CHECK. That the page actually renders a hint. That is one step further than a
 * scan can honestly go, so `skipped-currencies-hint.test.tsx` renders every page that reads the field
 * and asserts the warning names the codes.
 */

const REPO = join(__dirname, '..', '..', '..', '..');
const API_SCHEMAS = join(REPO, 'apps', 'api', 'app', 'schemas');
const WEB_API = join(REPO, 'apps', 'web', 'lib', 'api');

const FIELD = 'skipped_currencies';

// An API schema module maps to a web api module by name: `payments_calendar.py` ↔
// `payments-calendar.ts`. Derived rather than listed, so a new feature is covered by existing.
function webModuleFor(pythonModule: string): string[] {
  const base = pythonModule.replace(/\.py$/, '');
  const kebab = base.replace(/_/g, '-');
  // The web pluralises some modules (`expense.py` ↔ `expenses.ts`), so both spellings are accepted —
  // whichever exists. Only the ABSENCE of both is a failure.
  return [`${kebab}.ts`, `${kebab}s.ts`];
}

function apiModulesDeclaringTheField(): string[] {
  return readdirSync(API_SCHEMAS)
    .filter((f) => f.endsWith('.py'))
    .filter((f) => readFileSync(join(API_SCHEMAS, f), 'utf8').includes(FIELD));
}

// How many response classes in a Python schema module declare the field as a class attribute. Split
// on top-level `class` statements so each block is one class body; a mention in a comment or a
// docstring-like `#` line does not count, only an indented `skipped_currencies:` annotation.
function apiResponsesDeclaringTheField(pythonModule: string): number {
  const source = readFileSync(join(API_SCHEMAS, pythonModule), 'utf8');
  const declaration = new RegExp(`^\\s+${FIELD}\\s*:`, 'm');
  return source
    .split(/^class /m)
    .slice(1)
    .filter((body) => declaration.test(body)).length;
}

// The web api module an API schema module maps to, or null when the web consumes none of it.
function existingWebModuleFor(pythonModule: string): string | null {
  const webFiles = new Set(readdirSync(WEB_API));
  return webModuleFor(pythonModule).find((f) => webFiles.has(f)) ?? null;
}

describe('every API response carrying skipped_currencies is read by the web', () => {
  it('has a web api module declaring the field for each API schema module that sends it', () => {
    const webFiles = new Set(readdirSync(WEB_API));
    const missing = apiModulesDeclaringTheField().filter((pythonModule) => {
      const candidates = webModuleFor(pythonModule).filter((f) => webFiles.has(f));
      // No web module at all means the web does not consume this endpoint, which is not a defect.
      if (candidates.length === 0) return false;
      // The DECLARATION, not the bare field name. A mapper line alone contains `skipped_currencies`
      // too, so matching the name let a raw interface lose the field while this still passed —
      // found by deleting it from the calendar's raw interface and watching this stay green.
      return !candidates.some((f) =>
        readFileSync(join(WEB_API, f), 'utf8').includes(`${FIELD}: string[]`),
      );
    });

    expect(missing).toEqual([]);
  });

  it('declares it on the frontend type as well as the raw one, wherever it appears', () => {
    // The raw interface alone would satisfy the check above while the mapper still dropped it on the
    // way to the page — which is exactly the shape of the bug, one layer down.
    const offenders = readdirSync(WEB_API)
      .filter((f) => f.endsWith('.ts'))
      .filter((f) => readFileSync(join(WEB_API, f), 'utf8').includes(FIELD))
      .filter((f) => !readFileSync(join(WEB_API, f), 'utf8').includes('skippedCurrencies'));

    expect(offenders).toEqual([]);
  });

  it('declares it on as many raw responses as the API module sends it on', () => {
    // The API is the other side of the count. Comparing the web with itself (declared vs mapped, below)
    // stays green when one response of a multi-response module loses the field from EVERY web layer
    // at once — raw, frontend type, mapper and the page's union — because each layer still agrees
    // with the others. Counting the Python response classes is what notices the fourth one is gone.
    const short: Record<string, [number, number]> = {};
    for (const pythonModule of apiModulesDeclaringTheField()) {
      const webModule = existingWebModuleFor(pythonModule);
      if (webModule === null) continue;
      const sent = apiResponsesDeclaringTheField(pythonModule);
      const text = readFileSync(join(WEB_API, webModule), 'utf8');
      const declared = text.split(`${FIELD}: string[]`).length - 1;
      if (declared < sent) short[`${pythonModule} -> ${webModule}`] = [sent, declared];
    }
    expect(short).toEqual({});
  });

  it('maps every raw occurrence rather than declaring it and forgetting the mapper', () => {
    // One `skipped_currencies` in a raw interface needs one `skippedCurrencies: raw.skipped_currencies`
    // in a mapper. This compares the web with ITSELF, so it catches a raw field with no mapper line (or
    // the reverse) — the case where a response is dropped from every layer at once is the API-side
    // count above.
    const mismatched: Record<string, [number, number]> = {};
    for (const file of readdirSync(WEB_API).filter((f) => f.endsWith('.ts'))) {
      const text = readFileSync(join(WEB_API, file), 'utf8');
      const declared = text.split(`${FIELD}: string[]`).length - 1;
      const mapped = text.split(`skippedCurrencies: raw.${FIELD}`).length - 1;
      // Both directions. `declared > 0 && mapped === 0` is a field read by nothing; the reverse is a
      // mapper reading a field its raw interface no longer declares, which TypeScript also catches —
      // but a guard that silently skips half its own condition is how the first version of this test
      // passed on the very defect it was written for.
      if ((declared > 0 || mapped > 0) && declared !== mapped)
        mismatched[file] = [declared, mapped];
    }
    expect(mismatched).toEqual({});
  });

  it('is actually looking at both trees', () => {
    // Anti-vacuity on both sides. Every assertion above passes perfectly against an empty list, and a
    // path that stopped resolving would produce exactly that.
    const apiModules = apiModulesDeclaringTheField();
    expect(apiModules.length).toBeGreaterThanOrEqual(6);
    expect(apiModules).toContain('finance_metrics.py');
    expect(apiModules).toContain('payments_calendar.py');
    // The class count's own anti-vacuity: the finance module sends the field on four responses.
    expect(apiResponsesDeclaringTheField('finance_metrics.py')).toBe(4);

    const webModules = readdirSync(WEB_API).filter((f) =>
      readFileSync(join(WEB_API, f), 'utf8').includes(FIELD),
    );
    expect(webModules.length).toBeGreaterThanOrEqual(6);
    expect(webModules).toContain('finance-metrics.ts');
  });
});
