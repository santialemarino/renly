import { readFileSync } from 'node:fs';
import { join } from 'node:path';
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
 * The code list is read from the API's own `errors.py` rather than restated here, because the failure
 * being guarded IS the drift: a restated list agrees with itself forever. A code that should
 * deliberately have no translation would need an explicit exemption with a reason; there are none.
 */
const ERRORS_PY = join(import.meta.dirname, '../../../api/app/domain/errors.py');

/*
 * The extra fields each code carries, read from the SAME file — an error's `extra` property IS its
 * payload contract. Reading it rather than restating it means the test asserts the real thing: that
 * every placeholder a message names is a field the API actually sends, in both directions. A
 * hand-written map drifts silently and, when I wrote one, was wrong for six codes while passing.
 */
function apiErrorPayloads(): Record<string, string[]> {
  const source = readFileSync(ERRORS_PY, 'utf8');
  const payloads: Record<string, string[]> = {};
  // Split on class boundaries so a `code` and an `extra` are only ever paired within one class.
  for (const block of source.split(/^class /m).slice(1)) {
    const code = /^\s*code = "([a-z_0-9]+)"/m.exec(block)?.[1];
    if (!code) continue;
    // `[\s\S]*?` rather than `\s*` before the return: one of these properties has a comment line in
    // between, and requiring only whitespace silently yielded an EMPTY payload for it — which read as
    // "this message takes no arguments" and let its unrendered placeholder through.
    const extra = /def extra\(self\) -> dict:[\s\S]*?return \{([\s\S]*?)\}/.exec(block)?.[1] ?? '';
    payloads[code] = [...extra.matchAll(/"([a-z_0-9]+)":/g)].map((match) => match[1] as string);
  }
  return payloads;
}

describe('API error codes are localized', () => {
  const payloads = apiErrorPayloads();
  const codes = Object.keys(payloads).sort();

  it('finds the API code list', () => {
    // A guard on the guard: a moved or renamed errors.py would otherwise make every case below vacuous.
    expect(codes.length).toBeGreaterThan(40);
    // And that the payload half is really being read, not defaulting to empty for everything.
    expect(Object.values(payloads).filter((keys) => keys.length > 0).length).toBeGreaterThan(10);
  });

  it.each(codes)('%s resolves in both locales', (code) => {
    const detail = `ENGLISH FALLBACK for ${code}`;
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
      const params = Object.fromEntries((payloads[code] ?? []).map((key) => [key, '1']));
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
  });
});
