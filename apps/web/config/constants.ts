/**
 * i18n / locale constants. Used by i18n/request.ts and for date/number formatting (e.g. LOCALE_MAP).
 */
export const DEFAULT_LOCALE = 'en';
export const SUPPORTED_LOCALES = ['en', 'es'] as const;

export const LOCALE_MAP = {
  en: 'en-US',
  es: 'es-AR',
} as const;

export const LOCALE_COOKIE = 'NEXT_LOCALE';
// One-year max-age — the cookie is the SSR locale signal; it should outlive sessions.
export const LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

export const ES_LOCALE = 'es';
export const EN_LOCALE = 'en';
