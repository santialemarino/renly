import { format } from 'date-fns';

import { dateTimeFormat, listFormat, numberFormat } from '@/lib/i18n/intl-cache';
import { getDateFnsLocale, getLocaleTag } from '@/lib/i18n/locales';

export interface FormatValueOptions {
  locale?: string;
  compact?: boolean;
  // Max fraction digits for non-compact output (ISO-4217 sub-unit precision when currency-driven).
  maxDecimals?: number;
}

// Formats a number with thousand separators, stripping .00 for integers. Pass `compact: true` for axis/tooltip-style abbreviated output (e.g. "1.5M", "23K"). The compact branch always caps at 1 fraction digit and ignores `maxDecimals` (which governs non-compact precision only).
export function formatValue(value: number, options: FormatValueOptions = {}): string {
  const { locale, compact = false, maxDecimals = 2 } = options;
  if (compact) {
    return numberFormat(getLocaleTag(locale), {
      notation: 'compact',
      compactDisplay: 'short',
      maximumFractionDigits: 1,
    }).format(value);
  }
  const hasDecimals = value % 1 !== 0;
  return numberFormat(getLocaleTag(locale), {
    minimumFractionDigits: 0,
    maximumFractionDigits: hasDecimals ? maxDecimals : 0,
  }).format(value);
}

// Formats a number with an explicit +/- sign and thousand separators. `signDisplay: 'exceptZero'` is evaluated against the ROUNDED value, so a magnitude that rounds to zero (e.g. -0.004 at 2 decimals) renders "0" — never a spurious "-0"/"+0".
export function formatSignedValue(value: number, locale?: string): string {
  const hasDecimals = value % 1 !== 0;
  return numberFormat(getLocaleTag(locale), {
    minimumFractionDigits: 0,
    maximumFractionDigits: hasDecimals ? 2 : 0,
    signDisplay: 'exceptZero',
  }).format(value);
}

// Formats a decimal ratio as a signed percentage (e.g. 0.05 → "+5%", -0.052 → "-5.2%"). Zero renders without a sign.
export function formatSignedPct(pct: number, locale?: string): string {
  return numberFormat(getLocaleTag(locale), {
    style: 'percent',
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
    signDisplay: 'exceptZero',
  }).format(pct);
}

// Formats a percentage value (already in percent units) for display, dropping decimals when exact (e.g. 40 → "40", 33.5 → "33.5"). No `%` suffix — callers append it.
export function formatPct(value: number, locale?: string): string {
  return numberFormat(getLocaleTag(locale), {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(value);
}

// Formats a decimal ratio as a percentage string (e.g. 0.2 → "20%", 0.205 → "20.5%").
export function formatRatePct(pct: number, locale?: string): string {
  return numberFormat(getLocaleTag(locale), {
    style: 'percent',
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(pct);
}

// Formats a plain ratio with a fixed two decimals (e.g. 1.5 → "1.50", 2 → "2.00"). Unlike formatValue, trailing zeros are kept so ratios read consistently. No unit suffix — callers append it (e.g. "x").
export function formatRatio(value: number, locale?: string): string {
  return numberFormat(getLocaleTag(locale), {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

/*
 * An ownership percentage, at a FIXED two decimals (e.g. 13.91 → "13.91", 50 → "50.00"). No `%`
 * suffix — callers append it, like formatPct.
 *
 * Distinct from formatPct, which caps at ONE decimal: a co-ownership split is computed to two, with the
 * rounding remainder assigned to the largest holder so the displayed parts sum to exactly 100. Render
 * it at one decimal and a three-way 33.33/33.33/33.34 split reads as 33.3/33.3/33.3 — parts that
 * visibly fail to add up, which is the exact failure the remainder rule exists to prevent.
 *
 * Delegates to formatRatio because the two rules agree today, and stays a separate function because
 * they are separate rules: a ratio is a unitless multiple, a share is a percentage that must total 100.
 * A change to either must not silently move the other.
 */
export function formatSharePct(value: number, locale?: string): string {
  return formatRatio(value, locale);
}

// Returns the color class: green for positive, red for negative, grey for zero/null.
export function valueColor(value: number | null): string {
  if (value === null || value === 0) return 'text-muted-foreground';
  return value > 0 ? 'text-emerald-600' : 'text-red-500';
}

/*
 * Date formatters split by engine on purpose: `formatDateForLocale` uses date-fns for its `PP`
 * token (locale-ordered day-month-year, which dodges DD/MM vs MM/DD ambiguity); every other date
 * label passes EXPLICIT field options ({month, day, weekday, year}) whose ordering is unambiguous,
 * so they use `Intl.DateTimeFormat` (via the cache) — and `formatTimestampDate` needs Intl anyway
 * for its IANA-timezone shift, which date-fns core can't do. All date-only helpers anchor at local
 * midnight and are never timezone-shifted; only `formatTimestampDate` carries a timeZone.
 */

// Formats a date string (YYYY-MM-DD) as a short month label (e.g. "Jan 25" / "ene 25"). Date-only — never timezone-shifted.
export function formatMonth(dateStr: string, locale?: string): string {
  const date = new Date(dateStr + 'T00:00:00');
  return dateTimeFormat(getLocaleTag(locale), { month: 'short', year: '2-digit' }).format(date);
}

// Formats the long month name for a (year, 1-based month) pair (e.g. "May" / "mayo"). Date-only — never timezone-shifted.
export function formatMonthLong(year: number, month: number, locale?: string): string {
  return dateTimeFormat(getLocaleTag(locale), { month: 'long' }).format(
    new Date(year, month - 1, 1),
  );
}

// Formats a date string (YYYY-MM-DD) as a short month + full year (e.g. "Jan 2025" / "ene 2025"). Date-only — never timezone-shifted. Distinct from formatMonth's 2-digit year (used for statement-period labels).
export function formatMonthYear(dateStr: string, locale?: string): string {
  const date = new Date(dateStr + 'T00:00:00');
  return dateTimeFormat(getLocaleTag(locale), { month: 'short', year: 'numeric' }).format(date);
}

// Formats a date string (YYYY-MM-DD) as a long weekday + day-of-month (e.g. "Monday 5" / "lunes 5"). Date-only — never timezone-shifted.
export function formatWeekdayDay(dateStr: string, locale?: string): string {
  const date = new Date(dateStr + 'T00:00:00');
  return dateTimeFormat(getLocaleTag(locale), { weekday: 'long', day: 'numeric' }).format(date);
}

// Formats an ISO date string (YYYY-MM-DD) as a locale-aware medium-style label (e.g. "Jan 2, 2025" / "2 ene 2025") via date-fns's 'PP' token. Day-month-year ordering in every supported locale sidesteps DD/MM vs MM/DD ambiguity. Pass an alternate format token to override.
export function formatDateForLocale(
  iso: string,
  locale?: string,
  dateFormat: string = 'PP',
): string {
  const date = new Date(iso + 'T00:00:00');
  return format(date, dateFormat, { locale: getDateFnsLocale(locale) });
}

// Formats a full ISO timestamp (e.g. "2026-07-16T12:00:00Z") as a short, locale-aware date label (e.g. "Jul 16, 2026" / "16 jul 2026"), dropping the time. Renders in `timeZone` when given (the user's stored zone) so the calendar day is correct for the viewer; falls back to the ambient zone otherwise. For date-only (YYYY-MM-DD) strings use formatDateForLocale — those must stay on the local-midnight anchor and must NOT be timezone-shifted.
export function formatTimestampDate(iso: string, locale?: string, timeZone?: string): string {
  return dateTimeFormat(getLocaleTag(locale), {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone,
  }).format(new Date(iso));
}

// Formats a number as a compact value for chart Y axes and tooltips (e.g. 1500000 → "1.5M", 23000 → "23K").
export function formatAxisValue(value: number, locale?: string): string {
  return formatValue(value, { locale, compact: true });
}

// Formats a list of strings into a locale-aware conjunction (e.g. "a, b, and c" / "a, b y c"). Empty → "", single → the item itself.
export function formatList(items: Iterable<string>, locale?: string): string {
  return listFormat(getLocaleTag(locale), {
    style: 'long',
    type: 'conjunction',
  }).format(items);
}
