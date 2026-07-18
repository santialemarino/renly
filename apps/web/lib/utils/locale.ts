import { getLocaleTag } from '@/lib/i18n/locales';

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
