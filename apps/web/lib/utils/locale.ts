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
