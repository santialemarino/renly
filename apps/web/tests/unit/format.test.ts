import { describe, expect, it } from 'vitest';

import {
  formatAxisValue,
  formatDateForLocale,
  formatList,
  formatMonth,
  formatMonthLong,
  formatMonthYear,
  formatPct,
  formatRatePct,
  formatRatio,
  formatSharePct,
  formatSignedPct,
  formatSignedValue,
  formatTimestampDate,
  formatValue,
  formatWeekdayDay,
  valueColor,
} from '@/lib/i18n/format';

describe('formatValue', () => {
  it('groups thousands per locale and strips .00 for integers', () => {
    expect(formatValue(1000, { locale: 'en' })).toBe('1,000');
    expect(formatValue(1000, { locale: 'es' })).toBe('1.000');
    expect(formatValue(1234.5, { locale: 'en' })).toBe('1,234.5');
    expect(formatValue(1234.5, { locale: 'es' })).toBe('1.234,5');
  });

  it('caps fraction digits at maxDecimals (default 2)', () => {
    expect(formatValue(1234.567, { locale: 'en' })).toBe('1,234.57');
    expect(formatValue(1234.567, { locale: 'en', maxDecimals: 3 })).toBe('1,234.567');
    expect(formatValue(1234.567, { locale: 'en', maxDecimals: 0 })).toBe('1,235');
  });

  it('renders compact notation', () => {
    expect(formatValue(1500000, { locale: 'en', compact: true })).toBe('1.5M');
    expect(formatValue(23000, { locale: 'en', compact: true })).toBe('23K');
  });
});

describe('formatSignedValue', () => {
  it('prefixes an explicit sign, no sign for zero', () => {
    expect(formatSignedValue(1234, 'en')).toBe('+1,234');
    expect(formatSignedValue(-1234, 'en')).toBe('-1,234');
    expect(formatSignedValue(0, 'en')).toBe('0');
  });

  it('renders a magnitude that rounds to zero as unsigned "0" (never "-0"/"+0")', () => {
    expect(formatSignedValue(-0.004, 'en')).toBe('0');
    expect(formatSignedValue(0.004, 'en')).toBe('0');
  });

  it('keeps decimals and the sign for genuinely non-zero fractional values', () => {
    expect(formatSignedValue(-1234.5, 'en')).toBe('-1,234.5');
    expect(formatSignedValue(-0.006, 'en')).toBe('-0.01');
    expect(formatSignedValue(1234.5, 'es')).toBe('+1.234,5');
  });
});

describe('percentage formatters', () => {
  it('formatSignedPct signs a ratio, zero unsigned', () => {
    expect(formatSignedPct(0.05, 'en')).toBe('+5%');
    expect(formatSignedPct(-0.052, 'en')).toBe('-5.2%');
    expect(formatSignedPct(0, 'en')).toBe('0%');
  });

  it('formatPct returns a bare number string', () => {
    expect(formatPct(40, 'en')).toBe('40');
    expect(formatPct(33.5, 'en')).toBe('33.5');
  });

  it('formatRatePct renders a ratio as a percent', () => {
    expect(formatRatePct(0.2, 'en')).toBe('20%');
    expect(formatRatePct(0.205, 'en')).toBe('20.5%');
  });
});

describe('formatRatio', () => {
  it('keeps a fixed two decimals per locale', () => {
    expect(formatRatio(1.5, 'en')).toBe('1.50');
    expect(formatRatio(1.5, 'es')).toBe('1,50');
    expect(formatRatio(2, 'en')).toBe('2.00');
    expect(formatRatio(1234.5, 'es')).toBe('1.234,50');
  });
});

describe('formatSharePct', () => {
  it('keeps two decimals so the parts of a split sum to exactly 100', () => {
    // The reason it is not formatPct: at one decimal these three read 33.3 / 33.3 / 33.3 and visibly
    // fail to add up, which is the failure the backend's remainder-to-the-largest-holder rule exists
    // to prevent in the first place.
    expect(['33.33', '33.33', '33.34'].map((v) => formatSharePct(Number(v), 'en'))).toEqual([
      '33.33',
      '33.33',
      '33.34',
    ]);
    expect(formatSharePct(50, 'en')).toBe('50.00');
    expect(formatSharePct(13.91, 'es')).toBe('13,91');
  });
});

describe('formatList', () => {
  it('joins with a locale-aware conjunction', () => {
    expect(formatList(['A', 'B', 'C'], 'en')).toBe('A, B, and C');
    expect(formatList(['A', 'B', 'C'], 'es')).toBe('A, B y C');
    expect(formatList(['A', 'B'], 'en')).toBe('A and B');
    expect(formatList(['A', 'B'], 'es')).toBe('A y B');
  });

  it('returns the single item alone and an empty list as ""', () => {
    expect(formatList(['Solo'], 'en')).toBe('Solo');
    expect(formatList([], 'en')).toBe('');
  });
});

describe('valueColor', () => {
  it('maps sign to a color class', () => {
    expect(valueColor(5)).toBe('text-emerald-600');
    expect(valueColor(-5)).toBe('text-red-500');
    expect(valueColor(0)).toBe('text-muted-foreground');
    expect(valueColor(null)).toBe('text-muted-foreground');
  });
});

describe('date formatters', () => {
  it('formatDateForLocale renders unambiguous named-month dates per locale', () => {
    expect(formatDateForLocale('2025-04-29', 'en')).toBe('Apr 29, 2025');
    const es = formatDateForLocale('2025-04-29', 'es');
    expect(es).toContain('abr');
    expect(es).toContain('29');
    expect(es).toContain('2025');
  });

  it('formatMonth renders a short month + 2-digit year', () => {
    expect(formatMonth('2025-01-15', 'en')).toBe('Jan 25');
    expect(formatMonth('2025-01-15', 'es')).toContain('ene');
  });

  it('formatMonthLong renders the long month for a (year, 1-based month) pair', () => {
    expect(formatMonthLong(2025, 5, 'en')).toBe('May');
    expect(formatMonthLong(2025, 1, 'en')).toBe('January');
    expect(formatMonthLong(2025, 5, 'es')).toBe('mayo');
  });

  it('formatMonthYear renders a short month + full year (distinct from formatMonth)', () => {
    expect(formatMonthYear('2025-01-31', 'en')).toBe('Jan 2025');
    const es = formatMonthYear('2025-01-31', 'es');
    expect(es).toContain('ene');
    expect(es).toContain('2025');
  });

  it('formatWeekdayDay renders the long weekday + day-of-month', () => {
    // 2025-01-06 is a Monday. Field ordering follows the locale's CLDR pattern, so assert parts.
    const en = formatWeekdayDay('2025-01-06', 'en');
    expect(en).toContain('Monday');
    expect(en).toContain('6');
    expect(formatWeekdayDay('2025-01-06', 'es')).toContain('lunes');
  });

  it('formatTimestampDate drops the time to a short date', () => {
    const en = formatTimestampDate('2026-07-16T12:00:00', 'en');
    expect(en).toContain('Jul');
    expect(en).toContain('16');
    expect(en).toContain('2026');
  });

  it('formatTimestampDate renders the calendar day in the given timezone', () => {
    // 02:00 UTC on Jul 16 is still Jul 15 in Los Angeles (UTC-7) but Jul 16 in Sydney (UTC+10).
    expect(formatTimestampDate('2026-07-16T02:00:00Z', 'en', 'America/Los_Angeles')).toBe(
      'Jul 15, 2026',
    );
    expect(formatTimestampDate('2026-07-16T02:00:00Z', 'en', 'Australia/Sydney')).toBe(
      'Jul 16, 2026',
    );
    expect(formatTimestampDate('2026-07-16T02:00:00Z', 'en', 'UTC')).toBe('Jul 16, 2026');
  });

  it('formatDateForLocale is date-only and never timezone-shifted (stays on the local-midnight anchor)', () => {
    // A YYYY-MM-DD value renders its own calendar day regardless of any ambient/stored tz.
    expect(formatDateForLocale('2026-07-16', 'en')).toBe('Jul 16, 2026');
  });
});

describe('formatAxisValue', () => {
  it('is compact by construction', () => {
    expect(formatAxisValue(1500000, 'en')).toBe('1.5M');
    expect(formatAxisValue(23000, 'en')).toBe('23K');
  });
});
