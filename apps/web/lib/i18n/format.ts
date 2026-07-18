import { format } from 'date-fns';

import { getDateFnsLocale, getLocaleTag } from '@/lib/i18n/locales';

export interface FormatValueOptions {
  locale?: string;
  compact?: boolean;
  // Max fraction digits for non-compact output (ISO-4217 sub-unit precision when currency-driven).
  maxDecimals?: number;
}

// Formats a number with thousand separators, stripping .00 for integers. Pass `compact: true` for axis/tooltip-style abbreviated output (e.g. "1.5M", "23K").
export function formatValue(value: number, options: FormatValueOptions = {}): string {
  const { locale, compact = false, maxDecimals = 2 } = options;
  if (compact) {
    return new Intl.NumberFormat(getLocaleTag(locale), {
      notation: 'compact',
      compactDisplay: 'short',
      maximumFractionDigits: 1,
    }).format(value);
  }
  const hasDecimals = value % 1 !== 0;
  return new Intl.NumberFormat(getLocaleTag(locale), {
    minimumFractionDigits: 0,
    maximumFractionDigits: hasDecimals ? maxDecimals : 0,
  }).format(value);
}

// Formats a number with explicit +/- sign and thousand separators. Zero renders without a sign.
export function formatSignedValue(value: number, locale?: string): string {
  const formatted = formatValue(Math.abs(value), { locale });
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `-${formatted}`;
  return formatted;
}

// Formats a decimal ratio as a signed percentage (e.g. 0.05 → "+5%", -0.052 → "-5.2%"). Zero renders without a sign.
export function formatSignedPct(pct: number, locale?: string): string {
  return new Intl.NumberFormat(getLocaleTag(locale), {
    style: 'percent',
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
    signDisplay: 'exceptZero',
  }).format(pct);
}

// Formats a percentage value (already in percent units) for display, dropping decimals when exact (e.g. 40 → "40", 33.5 → "33.5"). No `%` suffix — callers append it.
export function formatPct(value: number, locale?: string): string {
  return new Intl.NumberFormat(getLocaleTag(locale), {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(value);
}

// Formats a decimal ratio as a percentage string (e.g. 0.2 → "20%", 0.205 → "20.5%").
export function formatRatePct(pct: number, locale?: string): string {
  return new Intl.NumberFormat(getLocaleTag(locale), {
    style: 'percent',
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(pct);
}

// Returns the color class: green for positive, red for negative, grey for zero/null.
export function valueColor(value: number | null): string {
  if (value === null || value === 0) return 'text-muted-foreground';
  return value > 0 ? 'text-emerald-600' : 'text-red-500';
}

// Formats a date string (YYYY-MM-DD) as a short month label (e.g. "Jan 25" / "ene 25").
export function formatMonth(dateStr: string, locale?: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString(getLocaleTag(locale), { month: 'short', year: '2-digit' });
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

// Formats a full ISO timestamp (e.g. "2026-07-16T12:00:00") as a short, locale-aware date label (e.g. "Jul 16, 2026" / "16 jul 2026"), dropping the time. For date-only (YYYY-MM-DD) strings use formatDateForLocale.
export function formatTimestampDate(iso: string, locale?: string): string {
  return new Date(iso).toLocaleDateString(getLocaleTag(locale), {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

// Formats a number as a compact value for chart Y axes and tooltips (e.g. 1500000 → "1.5M", 23000 → "23K").
export function formatAxisValue(value: number, locale?: string): string {
  return formatValue(value, { locale, compact: true });
}
