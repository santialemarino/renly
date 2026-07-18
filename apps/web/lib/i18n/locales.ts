import type { Locale as DateFnsLocale } from 'date-fns';
import { enUS, es } from 'date-fns/locale';

import { COOKIE_MAX_AGE_1_YEAR } from '@/config/constants';

/*
 * Single source of truth for every supported UI locale. Adding a language is one
 * entry here plus a matching `translations/<code>.json` file — the BCP47 tag, the
 * date-fns locale, the self-language label, the text direction, `SUPPORTED_LOCALES`,
 * the language-picker options, and the browser-language mapper all derive from this.
 */
export const LOCALES = [
  { code: 'en', bcp47: 'en-US', dateFns: enUS, label: 'English', dir: 'ltr' },
  { code: 'es', bcp47: 'es-AR', dateFns: es, label: 'Español', dir: 'ltr' },
] as const;

export type Locale = (typeof LOCALES)[number]['code'];
export type TextDirection = (typeof LOCALES)[number]['dir'];

// Default locale used when no cookie, header, or stored preference resolves to a supported one.
export const DEFAULT_LOCALE: Locale = 'en';

// Supported locale codes as a non-empty tuple so `z.enum(SUPPORTED_LOCALES)` keeps its literal types. LOCALES is a non-empty `as const`, so the tuple cast is sound.
export const SUPPORTED_LOCALES = LOCALES.map((l) => l.code) as [Locale, ...Locale[]];

// DEFAULT_LOCALE is always present in LOCALES, so this is never undefined.
const DEFAULT_ENTRY = LOCALES.find((l) => l.code === DEFAULT_LOCALE)!;

// Registry entry for a code, or the default-locale entry when the code is missing or unmapped.
function localeEntry(locale?: string): (typeof LOCALES)[number] {
  return LOCALES.find((l) => l.code === locale) ?? DEFAULT_ENTRY;
}

// Resolves a short locale code (e.g. 'en', 'es') to a BCP47 tag (e.g. 'en-US', 'es-AR') for Intl APIs. Falls back to the default locale's tag when input is missing or unmapped.
export function getLocaleTag(locale?: string): string {
  return localeEntry(locale).bcp47;
}

// Resolves a short locale code to a date-fns Locale object for `format()`, `parse()`, and react-day-picker's `<Calendar locale={...}>`. Falls back to the default locale.
export function getDateFnsLocale(locale?: string): DateFnsLocale {
  return localeEntry(locale).dateFns;
}

// Resolves a short locale code to its text direction ('ltr' | 'rtl'). Falls back to the default locale. Every supported locale is 'ltr' today; the field readies the registry for a future RTL language.
export function getLocaleDirection(locale?: string): TextDirection {
  return localeEntry(locale).dir;
}

// Language-picker options: the self-language label ("English" stays "English", "Español" stays "Español") regardless of the active locale — standard convention for language pickers.
export const LANGUAGE_OPTIONS = LOCALES.map((l) => ({ value: l.code, label: l.label }));

// Language selection mode: 'auto' follows the browser language, 'manual' pins the user's explicit choice.
export const LANGUAGE_MODE_AUTO = 'auto';
export const LANGUAGE_MODE_MANUAL = 'manual';
export const LANGUAGE_MODES = [LANGUAGE_MODE_AUTO, LANGUAGE_MODE_MANUAL] as const;
export type LanguageMode = (typeof LANGUAGE_MODES)[number];

// Cookie carrying the active locale across requests — read by i18n/request.ts, written by the localization and language-auto-sync actions.
export const LOCALE_COOKIE = 'NEXT_LOCALE';
export const LOCALE_COOKIE_MAX_AGE = COOKIE_MAX_AGE_1_YEAR;

// Maps a browser BCP47 string (e.g. 'es-AR', 'en-US', 'pt-BR') to a supported locale by stripping the country suffix. Falls back to DEFAULT_LOCALE when the language prefix isn't supported.
export function mapBrowserLanguageToSupported(bcp47: string): Locale {
  const prefix = bcp47.toLowerCase().split('-')[0];
  const match = LOCALES.find((l) => l.code === prefix);
  return match ? match.code : DEFAULT_LOCALE;
}

// Returns the browser's detected language mapped to a supported locale. Safe to call on both server and client; returns DEFAULT_LOCALE when navigator is unavailable.
export function detectBrowserLanguage(): Locale {
  if (typeof navigator === 'undefined') return DEFAULT_LOCALE;
  return mapBrowserLanguageToSupported(navigator.language || DEFAULT_LOCALE);
}
