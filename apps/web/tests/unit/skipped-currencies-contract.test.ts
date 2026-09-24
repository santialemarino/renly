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
 * scan can honestly go, so it is covered by the e2e spec instead.
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

  it('maps every raw occurrence rather than declaring it and forgetting the mapper', () => {
    // One `skipped_currencies` in a raw interface needs one `skippedCurrencies: raw.skipped_currencies`
    // in a mapper. Counting is what catches a fifth response added beside four that are wired.
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

    const webModules = readdirSync(WEB_API).filter((f) =>
      readFileSync(join(WEB_API, f), 'utf8').includes(FIELD),
    );
    expect(webModules.length).toBeGreaterThanOrEqual(6);
    expect(webModules).toContain('finance-metrics.ts');
  });
});
