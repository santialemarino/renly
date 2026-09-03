import { formatAmount } from '@/lib/i18n/currency';
import {
  formatAxisValue,
  formatDateForLocale,
  formatDayMonth,
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
  type FormatValueOptions,
} from '@/lib/i18n/format';

/*
 * The locale-bound formatter set. Every method closes over the resolved locale (and the user's
 * timezone, for full-ISO timestamps) so call sites never thread them (removing the silent en-US
 * default footgun). Pure — no React, no next-intl — so both the client hook (`useFormatters`) and
 * the server helper (`getFormatters`) reuse it.
 */
export function createFormatters(locale: string, timeZone?: string) {
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
    ratio: (value: number) => formatRatio(value, locale),
    sharePct: (value: number) => formatSharePct(value, locale),
    month: (dateStr: string) => formatMonth(dateStr, locale),
    monthLong: (year: number, month: number) => formatMonthLong(year, month, locale),
    monthYear: (dateStr: string) => formatMonthYear(dateStr, locale),
    dayMonth: (dateStr: string) => formatDayMonth(dateStr, locale),
    weekdayDay: (dateStr: string) => formatWeekdayDay(dateStr, locale),
    date: (iso: string, dateFormat?: string) => formatDateForLocale(iso, locale, dateFormat),
    timestampDate: (iso: string) => formatTimestampDate(iso, locale, timeZone),
    axisValue: (value: number) => formatAxisValue(value, locale),
    list: (items: Iterable<string>) => formatList(items, locale),
  };
}

export type Formatters = ReturnType<typeof createFormatters>;
