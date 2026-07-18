import { describe, expect, it } from 'vitest';

import {
  formatAxisValue,
  formatDateForLocale,
  formatMonth,
  formatPct,
  formatRatePct,
  formatSignedPct,
  formatSignedValue,
  formatTimestampDate,
  formatValue,
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

  it('formatTimestampDate drops the time to a short date', () => {
    const en = formatTimestampDate('2026-07-16T12:00:00', 'en');
    expect(en).toContain('Jul');
    expect(en).toContain('16');
    expect(en).toContain('2026');
  });
});

describe('formatAxisValue', () => {
  it('is compact by construction', () => {
    expect(formatAxisValue(1500000, 'en')).toBe('1.5M');
    expect(formatAxisValue(23000, 'en')).toBe('23K');
  });
});
