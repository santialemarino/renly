import { createTranslator } from 'next-intl';
import { describe, expect, it } from 'vitest';

import {
  decodeApiError,
  encodeApiError,
  parseApiError,
  resolveApiError,
  type ApiErrorTranslator,
} from '@/lib/i18n/api-errors';
import en from '../../translations/en.json';
import es from '../../translations/es.json';

// A fake `apiErrors` translator over a small map, mirroring next-intl's callable + `.has` shape.
function fakeTranslator(messages: Record<string, string>): ApiErrorTranslator {
  const t = ((code: string, values?: Record<string, string | number>) => {
    const template = messages[code] ?? code;
    return template.replace(/\{(\w+)\}/g, (_m, key) => String(values?.[key] ?? `{${key}}`));
  }) as ApiErrorTranslator;
  t.has = (code: string) => code in messages;
  return t;
}

function fakeResponse(body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { headers });
}

const RATE_LIMITED = {
  detail: 'Too many requests. Please slow down and try again later.',
  code: 'rate_limited',
};

describe('parseApiError', () => {
  it('splits detail, code, and extra params', async () => {
    const err = await parseApiError(
      fakeResponse({
        detail: 'nope',
        code: 'investment_currency_mismatch',
        row_currency: 'USD',
        base_currency: 'ARS',
      }),
    );
    expect(err.code).toBe('investment_currency_mismatch');
    expect(err.detail).toBe('nope');
    expect(err.params).toEqual({ row_currency: 'USD', base_currency: 'ARS' });
  });

  it('tolerates a missing code / non-JSON body', async () => {
    expect(await parseApiError(fakeResponse({ detail: 'x' }))).toEqual({
      code: undefined,
      detail: 'x',
      params: {},
    });
    expect(await parseApiError(new Response('not json'))).toEqual({ params: {} });
  });

  it('reads the wait from Retry-After as whole minutes, rounded up', async () => {
    for (const [seconds, minutes] of [
      ['0', 1],
      ['1', 1],
      ['60', 1],
      ['61', 2],
      ['3540', 59],
    ] as const) {
      const err = await parseApiError(fakeResponse(RATE_LIMITED, { 'Retry-After': seconds }));
      expect(err.params, `Retry-After: ${seconds}`).toEqual({ retry_after_minutes: minutes });
    }
  });

  it('adds no wait when Retry-After is absent or not a number of seconds', async () => {
    expect((await parseApiError(fakeResponse(RATE_LIMITED))).params).toEqual({});
    const dated = fakeResponse(RATE_LIMITED, { 'Retry-After': 'Wed, 21 Oct 2026 07:28:00 GMT' });
    expect((await parseApiError(dated)).params).toEqual({});
  });
});

describe('a rate-limited response reads as itself, in both locales', () => {
  // The whole path a form takes: parse the 429, resolve it against the real messages.
  it.each([
    ['en', en, '90', 'Too many attempts. Try again in 2 minutes.'],
    ['en', en, '30', 'Too many attempts. Try again in 1 minute.'],
    ['es', es, '90', 'Demasiados intentos. Probá de nuevo en 2 minutos.'],
    ['es', es, '30', 'Demasiados intentos. Probá de nuevo en 1 minuto.'],
  ] as const)('%s, Retry-After %s', async (locale, messages, retryAfter, expected) => {
    const t = createTranslator({ locale, messages, namespace: 'apiErrors' });
    const err = await parseApiError(fakeResponse(RATE_LIMITED, { 'Retry-After': retryAfter }));
    expect(resolveApiError(t as never, err, 'fallback')).toBe(expected);
  });
});

describe('encodeApiError / decodeApiError', () => {
  it('round-trips a coded error, numeric params staying numbers', () => {
    const error = {
      code: 'rate_limited',
      detail: 'Too many requests & more.',
      params: { retry_after_minutes: 3, row_currency: 'USD' },
    };
    expect(decodeApiError(encodeApiError(error))).toEqual(error);
  });

  it('decodes an ordinary Auth.js code, or nothing, to null', () => {
    expect(decodeApiError('credentials')).toBeNull();
    expect(decodeApiError(undefined)).toBeNull();
    expect(decodeApiError('')).toBeNull();
  });
});

describe('resolveApiError', () => {
  const t = fakeTranslator({
    has_linked_expenses: 'Archivá la tarjeta.',
    investment_currency_mismatch: 'La moneda {row_currency} no coincide con {base_currency}.',
  });

  it('returns the localized message for a mapped code', () => {
    expect(
      resolveApiError(
        t,
        { code: 'has_linked_expenses', detail: 'Archive it.', params: {} },
        'fallback',
      ),
    ).toBe('Archivá la tarjeta.');
  });

  it('interpolates extra params into the localized message', () => {
    expect(
      resolveApiError(
        t,
        {
          code: 'investment_currency_mismatch',
          detail: 'raw',
          params: { row_currency: 'USD', base_currency: 'ARS' },
        },
        'fallback',
      ),
    ).toBe('La moneda USD no coincide con ARS.');
  });

  it('falls back to the raw detail for an unmapped code', () => {
    expect(
      resolveApiError(
        t,
        { code: 'some_unmapped_code', detail: 'Raw English detail.', params: {} },
        'fallback',
      ),
    ).toBe('Raw English detail.');
  });

  it('falls back to the raw detail when there is no code', () => {
    expect(resolveApiError(t, { detail: 'Raw detail.', params: {} }, 'fallback')).toBe(
      'Raw detail.',
    );
  });

  it('uses the caller fallback when there is neither a mapped code nor a detail', () => {
    expect(resolveApiError(t, { code: 'some_unmapped_code', params: {} }, 'fallback')).toBe(
      'fallback',
    );
  });
});
