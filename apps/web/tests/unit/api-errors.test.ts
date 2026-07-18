import { describe, expect, it } from 'vitest';

import { parseApiError, resolveApiError, type ApiErrorTranslator } from '@/lib/i18n/api-errors';

// A fake `apiErrors` translator over a small map, mirroring next-intl's callable + `.has` shape.
function fakeTranslator(messages: Record<string, string>): ApiErrorTranslator {
  const t = ((code: string, values?: Record<string, string | number>) => {
    const template = messages[code] ?? code;
    return template.replace(/\{(\w+)\}/g, (_m, key) => String(values?.[key] ?? `{${key}}`));
  }) as ApiErrorTranslator;
  t.has = (code: string) => code in messages;
  return t;
}

function fakeResponse(body: unknown): Response {
  return { json: async () => body } as unknown as Response;
}

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
    const nonJson = {
      json: async () => {
        throw new Error('not json');
      },
    } as unknown as Response;
    expect(await parseApiError(nonJson)).toEqual({ params: {} });
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
