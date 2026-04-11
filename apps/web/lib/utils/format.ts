import { FORMAT_THRESHOLD_MILLION, FORMAT_THRESHOLD_THOUSAND } from '@/lib/constants/charts';

// Formats a number with thousand separators, stripping .00 for integers.
export function formatValue(value: number): string {
  const hasDecimals = value % 1 !== 0;
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: hasDecimals ? 2 : 0,
  }).format(value);
}

// Formats a number with explicit +/- sign and thousand separators.
export function formatSignedValue(value: number): string {
  const formatted = formatValue(Math.abs(value));
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `-${formatted}`;
  return formatted;
}

// Formats a decimal ratio as a signed percentage (e.g. 0.05 → "+5%", -0.052 → "-5.2%").
export function formatSignedPct(pct: number): string {
  const val = pct * 100;
  const hasDecimals = Math.round(val * 10) % 10 !== 0;
  const s = hasDecimals ? val.toFixed(1) : val.toFixed(0);
  return pct >= 0 ? `+${s}%` : `${s}%`;
}

// Formats a percentage value for display, dropping decimals when exact (e.g. 40 → "40", 33.5 → "33.5").
export function formatPct(value: number): string {
  const hasDecimals = Math.round(value * 10) % 10 !== 0;
  return hasDecimals ? value.toFixed(1) : value.toFixed(0);
}

// Formats a decimal ratio as a percentage string (e.g. 0.2 → "20%").
export function formatRatePct(pct: number): string {
  const val = pct * 100;
  const hasDecimals = Math.round(val * 10) % 10 !== 0;
  return hasDecimals ? `${val.toFixed(1)}%` : `${val.toFixed(0)}%`;
}

// Returns the color class: green for positive, red for negative, grey for zero/null.
export function valueColor(value: number | null): string {
  if (value === null || value === 0) return 'text-muted-foreground';
  return value > 0 ? 'text-emerald-600' : 'text-red-500';
}

// Formats a date string (YYYY-MM-DD) as "Jan 25".
export function formatMonth(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
}

// Formats a number as a compact value for chart Y axes (e.g. 1500000 → "1.5M").
export function formatAxisValue(value: number): string {
  if (value >= FORMAT_THRESHOLD_MILLION) return `${(value / FORMAT_THRESHOLD_MILLION).toFixed(1)}M`;
  if (value >= FORMAT_THRESHOLD_THOUSAND)
    return `${(value / FORMAT_THRESHOLD_THOUSAND).toFixed(0)}K`;
  return value.toFixed(0);
}
