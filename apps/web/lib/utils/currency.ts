import { getLocaleTag } from '@/lib/utils/locale';

// All currencies with exchange rate support.
const SUPPORTED_CONVERSION_CURRENCIES = new Set(['USD', 'ARS', 'BRL', 'EUR', 'GBP']);

export function isCurrencySupported(code: string): boolean {
  return SUPPORTED_CONVERSION_CURRENCIES.has(code);
}

// Formats a numeric string for display (thousand separators, strips .00 for integers).
export function formatAmount(value: string, locale?: string): string {
  const num = Number(value);
  if (isNaN(num)) return value;
  const hasDecimals = num % 1 !== 0;
  return new Intl.NumberFormat(getLocaleTag(locale), {
    minimumFractionDigits: 0,
    maximumFractionDigits: hasDecimals ? 2 : 0,
  }).format(num);
}
