import { describe, expect, it } from 'vitest';

import { formatAmount } from '@/lib/i18n/currency';

describe('formatAmount', () => {
  it('defaults to 2 fraction digits without a currency', () => {
    expect(formatAmount('1234.5', 'en')).toBe('1,234.5');
    expect(formatAmount('1234.567', 'en')).toBe('1,234.57');
  });

  it('uses ISO 4217 sub-unit precision when a currency is given', () => {
    expect(formatAmount('1234.567', 'en', 'USD')).toBe('1,234.57'); // 2 digits
    expect(formatAmount('1234.567', 'en', 'JPY')).toBe('1,235'); // 0 digits
    expect(formatAmount('1234.567', 'en', 'BHD')).toBe('1,234.567'); // 3 digits
  });

  it('strips .00 for whole numbers regardless of currency', () => {
    expect(formatAmount('1000', 'en', 'USD')).toBe('1,000');
  });

  it('applies the locale separators', () => {
    expect(formatAmount('1234.5', 'es', 'USD')).toBe('1.234,5');
  });

  it('returns the raw input for a non-numeric string', () => {
    expect(formatAmount('abc', 'en')).toBe('abc');
  });
});
