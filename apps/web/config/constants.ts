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
// One-year cookie max-age (seconds) — for preference cookies that should outlive sessions.
export const COOKIE_MAX_AGE_1_YEAR = 60 * 60 * 24 * 365;
export const LOCALE_COOKIE_MAX_AGE = COOKIE_MAX_AGE_1_YEAR;

/*
 * Sidebar progressive disclosure (UX-7): remembers a first-run newcomer's "Show more" choice.
 * Read server-side by the protected layout, written client-side by the sidebar. Lives here (a
 * neutral module) rather than in the sidebar so the server layout doesn't import a client module.
 */
export const SIDEBAR_EXPANDED_COOKIE = 'sidebar-expanded';

export const ES_LOCALE = 'es';
export const EN_LOCALE = 'en';
