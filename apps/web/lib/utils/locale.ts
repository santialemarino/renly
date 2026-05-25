import { DEFAULT_LOCALE, LOCALE_MAP } from '@/config/constants';

// Resolves a short locale code (e.g. 'en', 'es') to a BCP47 tag (e.g. 'en-US', 'es-AR') for Intl APIs. Falls back to the default locale's tag when input is missing or unmapped.
export function getLocaleTag(locale?: string): string {
  if (locale && locale in LOCALE_MAP) {
    return LOCALE_MAP[locale as keyof typeof LOCALE_MAP];
  }
  return LOCALE_MAP[DEFAULT_LOCALE];
}
