import cc from 'currency-codes';

import { formatValue } from '@/lib/utils/format';

// Formats a numeric string for display (thousand separators, strips .00 for integers). When `currency` is provided, uses ISO 4217 sub-unit precision (JPY/KRW → 0 decimals; BHD/IQD/KWD/OMR/JOD → 3; everything else → 2). Without a currency, falls back to 2 decimals.
export function formatAmount(value: string, locale?: string, currency?: string): string {
  const num = Number(value);
  if (isNaN(num)) return value;
  const digits = currency ? (cc.code(currency)?.digits ?? 2) : 2;
  return formatValue(num, { locale, maxDecimals: digits });
}
