import { formatAmount } from '@/lib/i18n/currency';
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
  type FormatValueOptions,
} from '@/lib/i18n/format';

/*
 * The locale-bound formatter set. Every method closes over the resolved locale so call sites
 * never thread it (removing the silent en-US default footgun). Pure — no React, no next-intl —
 * so both the client hook (`useFormatters`) and the server helper (`getFormatters`) reuse it.
 */
export function createFormatters(locale: string) {
  return {
    // The resolved locale, for the rare call site that still needs it directly (e.g. localeCompare).
    locale,
    value: (value: number, options?: Omit<FormatValueOptions, 'locale'>) =>
      formatValue(value, { ...options, locale }),
    amount: (value: string, currency?: string) => formatAmount(value, locale, currency),
    signedValue: (value: number) => formatSignedValue(value, locale),
    signedPct: (pct: number) => formatSignedPct(pct, locale),
    pct: (value: number) => formatPct(value, locale),
    ratePct: (pct: number) => formatRatePct(pct, locale),
    month: (dateStr: string) => formatMonth(dateStr, locale),
    date: (iso: string, dateFormat?: string) => formatDateForLocale(iso, locale, dateFormat),
    timestampDate: (iso: string) => formatTimestampDate(iso, locale),
    axisValue: (value: number) => formatAxisValue(value, locale),
  };
}

export type Formatters = ReturnType<typeof createFormatters>;
