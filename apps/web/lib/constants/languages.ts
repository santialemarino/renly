// Language constants and helpers. The supported set mirrors the i18n config in
// `config/constants.ts` (SUPPORTED_LOCALES) — kept duplicated locally so the constants
// file doesn't grow into a dependency hub.

import { DEFAULT_LOCALE, SUPPORTED_LOCALES } from '@/config/constants';

export const LANGUAGE_MODE_AUTO = 'auto';
export const LANGUAGE_MODE_MANUAL = 'manual';
export const LANGUAGE_MODES = [LANGUAGE_MODE_AUTO, LANGUAGE_MODE_MANUAL] as const;
export type LanguageMode = (typeof LANGUAGE_MODES)[number];

// Language options shown in the picker. Each label is self-language (English stays "English",
// Spanish stays "Español") regardless of the active locale — standard convention for language pickers.
export const LANGUAGE_OPTIONS = [
  { value: 'en', labelKey: 'en' },
  { value: 'es', labelKey: 'es' },
] as const;

// Maps a browser BCP47 string (e.g. 'es-AR', 'en-US', 'pt-BR') to a supported locale by
// stripping the country suffix. Falls back to DEFAULT_LOCALE when the language prefix isn't supported.
export function mapBrowserLanguageToSupported(bcp47: string): string {
  const prefix = bcp47.toLowerCase().split('-')[0];
  if (prefix && (SUPPORTED_LOCALES as readonly string[]).includes(prefix)) {
    return prefix;
  }
  return DEFAULT_LOCALE;
}

// Returns the browser's detected language mapped to a supported locale. Safe to call on
// both server and client; returns DEFAULT_LOCALE when navigator is unavailable.
export function detectBrowserLanguage(): string {
  if (typeof navigator === 'undefined') return DEFAULT_LOCALE;
  const browserLang = navigator.language || DEFAULT_LOCALE;
  return mapBrowserLanguageToSupported(browserLang);
}
