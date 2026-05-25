import type { Locale as DateFnsLocale } from 'date-fns';
import { enUS, es } from 'date-fns/locale';

import { DEFAULT_LOCALE, LOCALE_MAP } from '@/config/constants';

const DATE_FNS_LOCALE_MAP = {
  en: enUS,
  es,
};

// Resolves a short locale code (e.g. 'en', 'es') to a BCP47 tag (e.g. 'en-US', 'es-AR') for Intl APIs. Falls back to the default locale's tag when input is missing or unmapped.
export function getLocaleTag(locale?: string): string {
  if (locale && locale in LOCALE_MAP) {
    return LOCALE_MAP[locale as keyof typeof LOCALE_MAP];
  }
  return LOCALE_MAP[DEFAULT_LOCALE];
}

// Resolves a short locale code to a date-fns Locale object for `format()`, `parse()`, and react-day-picker's `<Calendar locale={...}>`. Falls back to the default locale when input is missing or unmapped.
export function getDateFnsLocale(locale?: string): DateFnsLocale {
  if (locale && locale in DATE_FNS_LOCALE_MAP) {
    return DATE_FNS_LOCALE_MAP[locale as keyof typeof DATE_FNS_LOCALE_MAP];
  }
  return DATE_FNS_LOCALE_MAP[DEFAULT_LOCALE];
}

// Returns the locale's decimal separator (e.g. '.' for en-US, ',' for es-AR).
export function getDecimalSeparator(locale?: string): string {
  const parts = new Intl.NumberFormat(getLocaleTag(locale)).formatToParts(1.5);
  return parts.find((p) => p.type === 'decimal')?.value ?? '.';
}

// Returns the locale's thousand-group separator (e.g. ',' for en-US, '.' for es-AR).
function getGroupSeparator(locale?: string): string {
  const parts = new Intl.NumberFormat(getLocaleTag(locale)).formatToParts(1234.5);
  return parts.find((p) => p.type === 'group')?.value ?? ',';
}

// Normalizes a user-typed locale-formatted amount string to canonical `.`-decimal. Strips thousand separators; replaces locale decimal separator with `.`. Used by `LocaleAmountInput` to convert display text to form-state canonical.
export function normalizeAmountFromInput(input: string, locale?: string): string {
  if (!input) return '';
  const group = getGroupSeparator(locale);
  const decimal = getDecimalSeparator(locale);
  return input.split(group).join('').replace(decimal, '.');
}

// Formats a canonical `.`-decimal amount string for display in a locale-aware input field. Replaces `.` with the locale's decimal separator. Does NOT add thousand separators (input fields show raw values).
export function formatAmountForInput(canonical: string, locale?: string): string {
  if (!canonical) return '';
  const decimal = getDecimalSeparator(locale);
  if (decimal === '.') return canonical;
  return canonical.replace('.', decimal);
}
