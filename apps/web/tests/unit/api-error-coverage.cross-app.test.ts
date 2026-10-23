import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { createTranslator } from 'next-intl';
import { describe, expect, it } from 'vitest';

import { resolveApiError } from '@/lib/i18n/api-errors';
import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * Every error code the API can answer with must resolve to a localized message in BOTH locales.
 *
 * Nothing else catches this. `resolveApiError` falls back to the backend's English `detail` for a code
 * it does not map — deliberately, so a new code degrades instead of crashing — which means a missing
 * key is invisible until a Spanish user hits that exact refusal and reads English. PR 3a shipped
 * thirteen unmapped codes and this file's first run caught a fourteenth that the hand-off list itself
 * had missed, on a form that is already live.
 *
 * The code list is read from the API's own source rather than restated here, because the failure
 * being guarded IS the drift: a restated list agrees with itself forever. A code that should
 * deliberately have no translation needs an entry in UNREACHABLE with a reason and a check that keeps
 * the reason true.
 */
const API_APP = join(import.meta.dirname, '../../../api/app');

/*
 * A code reaches a response body through four kinds of source, and the scan reads every `.py` file
 * under `app/` for all of them rather than naming the files:
 *   1. a `DomainError` subclass's class-level `code = "…"` (`domain/errors.py`), sent with its `extra`;
 *   2. a `CodedHTTPException(…, code="…")` raised by a router or dependency;
 *   3. a literal `{"code": "…"}` in a hand-built `JSONResponse` (the IntegrityError handler);
 *   4. a module constant passed as either (the body-size middleware's `_TOO_LARGE_CODE`).
 * Reading only `errors.py` missed eight codes that were translated by luck. Any other expression in a
 * `code=` / `"code":` position must be a PASSTHROUGH below or the scan fails, so a new way of emitting
 * a code cannot slip past it unread.
 */

// Expressions that forward a code derived elsewhere, keyed by file and expression.
const PASSTHROUGH: Record<string, string> = {
  'main.py: exc.code': 'the DomainError handler forwards the class-level code — source 1.',
  'main.py: code': 'the HTTPException handler forwards CodedHTTPException.code — source 2.',
};

// Codes the scan finds that no response can carry.
const UNREACHABLE: Record<string, string> = {
  domain_error:
    'the DomainError base default; only subclasses are raised (asserted: nothing constructs the base).',
};

interface ScannedCodes {
  // Each code's payload shapes: one per source, since the same code may be sent with different extras.
  payloads: Record<string, string[][]>;
  files: Record<string, Set<string>>;
  passthroughsSeen: Set<string>;
  unresolved: string[];
  constructsBase: string[];
}

// Every Python source file under `dir`.
function pythonFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry !== '__pycache__') out.push(...pythonFiles(full));
    } else if (entry.endsWith('.py')) out.push(full);
  }
  return out;
}

function scanApiErrorCodes(): ScannedCodes {
  const scanned: ScannedCodes = {
    payloads: {},
    files: {},
    passthroughsSeen: new Set(),
    unresolved: [],
    constructsBase: [],
  };
  const add = (code: string, file: string, payload: string[]) => {
    const variants = (scanned.payloads[code] ??= []);
    if (!variants.some((seen) => seen.join() === payload.join())) variants.push(payload);
    (scanned.files[code] ??= new Set()).add(file);
  };

  for (const path of pythonFiles(API_APP)) {
    const file = relative(API_APP, path);
    // Whole-line comments are prose, not code: errors.py's header quotes the response shape.
    const source = readFileSync(path, 'utf8').replace(/^\s*#.*$/gm, '');

    // Source 1: a class-level code, paired with an `extra` only within the same class.
    for (const block of source.split(/^class /m).slice(1)) {
      const code = /^\s+code(?:\s*:\s*str)?\s*=\s*"([a-z_0-9]+)"/m.exec(block)?.[1];
      if (!code) continue;
      // `[\s\S]*?` rather than `\s*` before the return: one of these properties has a comment line in
      // between, and requiring only whitespace silently yielded an EMPTY payload for it — which read as
      // "this message takes no arguments" and let its unrendered placeholder through.
      const extra =
        /def extra\(self\) -> dict:[\s\S]*?return \{([\s\S]*?)\}/.exec(block)?.[1] ?? '';
      add(
        code,
        file,
        [...extra.matchAll(/"([a-z_0-9]+)":/g)].map((match) => match[1] as string),
      );
    }

    // Sources 2–4: a `code=` keyword argument, a `"code":` dict entry or a `["code"] =` assignment.
    const sites =
      /(?:[(,]\s*code\s*=(?!=)|["']code["']\s*:|\[\s*["']code["']\s*\]\s*=(?!=))\s*([^,)}\n]+)/g;
    for (const [, raw] of source.matchAll(sites)) {
      const expr = (raw as string).trim();
      const literal = /^["']([a-z_0-9]+)["']$/.exec(expr)?.[1];
      const constant = /^[A-Za-z_]\w*$/.test(expr)
        ? new RegExp(`^${expr}\\s*(?::\\s*\\w+)?\\s*=\\s*["']([a-z_0-9]+)["']`, 'm').exec(
            source,
          )?.[1]
        : undefined;
      const code = literal ?? constant;
      if (code) add(code, file, []);
      else if (`${file}: ${expr}` in PASSTHROUGH) scanned.passthroughsSeen.add(`${file}: ${expr}`);
      else scanned.unresolved.push(`${file}: ${expr}`);
    }

    // Only a construction puts a paren straight after the name, bar the base's own `class` line.
    if (/(?<!class )\bDomainError\(/.test(source)) scanned.constructsBase.push(file);
  }
  return scanned;
}

describe('API error codes are localized', () => {
  const scanned = scanApiErrorCodes();
  const codes = Object.keys(scanned.payloads)
    .filter((code) => !(code in UNREACHABLE))
    .sort();
  const fromDomainErrors = codes.filter((code) => scanned.files[code]?.has('domain/errors.py'));

  it('derives the code list from every source', () => {
    // A guard on the guard: a moved directory or a narrowed scan would otherwise make every case
    // below vacuous. 95 domain-error codes plus 8 emitted outside errors.py as of U23.
    expect(codes.length).toBeGreaterThanOrEqual(103);
    expect(codes.length - fromDomainErrors.length).toBeGreaterThanOrEqual(8);
    // And that the payload half is really being read, not defaulting to empty for everything.
    expect(
      Object.values(scanned.payloads).filter((variants) => variants.some((keys) => keys.length > 0))
        .length,
    ).toBeGreaterThan(10);
  });

  it('understands every place a code is emitted', () => {
    // A code passed some other way (a variable, an attribute, an f-string) cannot be read statically:
    // resolve it to a literal or a module constant, or pin it in PASSTHROUGH with a reason.
    expect(scanned.unresolved).toEqual([]);
    expect([...scanned.passthroughsSeen].sort()).toEqual(Object.keys(PASSTHROUGH).sort());
  });

  it('keeps every UNREACHABLE reason true', () => {
    for (const code of Object.keys(UNREACHABLE)) expect(scanned.payloads).toHaveProperty(code);
    expect(scanned.constructsBase).toEqual([]);
  });

  it.each(codes)('%s resolves in both locales', (code) => {
    const detail = `ENGLISH FALLBACK for ${code}`;
    for (const payload of scanned.payloads[code] ?? []) {
      for (const [locale, messages] of [
        ['en', en],
        ['es', es],
      ] as const) {
        const t = createTranslator({ locale, messages, namespace: 'apiErrors' });
        /*
         * The extras go under `params`, which is where parseApiError puts them — spreading them at the
         * top level instead silently passes NO arguments, so every message with a placeholder is only
         * checked for existence. That was this test's own first bug, found by a mutation staying green.
         */
        const params = Object.fromEntries(payload.map((key) => [key, '1']));
        const resolved = resolveApiError(t as never, { code, detail, params }, '');
        // Falling back to `detail` is exactly the hole: the key is missing and the user reads English.
        expect(resolved, `apiErrors.${code} is missing from ${locale}.json`).not.toBe(detail);
        expect(resolved.length).toBeGreaterThan(0);
        // next-intl answers a message it cannot render with the key path, and leaves an unsubstituted
        // placeholder braced — so both mean the message names an argument the API does not send.
        expect(resolved, `apiErrors.${code} did not render in ${locale}`).not.toContain(
          `apiErrors.${code}`,
        );
        expect(resolved).not.toContain('{');
      }
    }
  });
});
