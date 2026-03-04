/**
 * i18n / locale constants. Used by i18n/request.ts and for date/number formatting (e.g. LOCALE_MAP).
 */
export const DEFAULT_LOCALE = 'en';
export const SUPPORTED_LOCALES = ['en', 'es'] as const;

export const LOCALE_MAP: Record<string, string> = {
  en: 'en-US',
  es: 'es-ES',
};

export const ES_LOCALE = 'es';
export const EN_LOCALE = 'en';
