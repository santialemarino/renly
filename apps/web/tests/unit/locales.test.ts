import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  DEFAULT_LOCALE,
  detectBrowserLanguage,
  getDateFnsLocale,
  getLocaleDirection,
  getLocaleTag,
  LANGUAGE_OPTIONS,
  mapBrowserLanguageToSupported,
  SUPPORTED_LOCALES,
} from '@/lib/i18n/locales';

describe('locale registry', () => {
  it('exposes the supported set derived from the registry', () => {
    expect(DEFAULT_LOCALE).toBe('en');
    expect([...SUPPORTED_LOCALES]).toEqual(['en', 'es']);
  });

  it('derives the language-picker options with self-language labels', () => {
    expect(LANGUAGE_OPTIONS).toEqual([
      { value: 'en', label: 'English' },
      { value: 'es', label: 'Español' },
    ]);
  });
});

describe('getLocaleTag', () => {
  it('maps short codes to BCP47 tags', () => {
    expect(getLocaleTag('en')).toBe('en-US');
    expect(getLocaleTag('es')).toBe('es-AR');
  });

  it('falls back to the default locale tag when missing or unmapped', () => {
    expect(getLocaleTag(undefined)).toBe('en-US');
    expect(getLocaleTag('fr')).toBe('en-US');
  });
});

describe('getDateFnsLocale', () => {
  it('maps short codes to date-fns locale objects', () => {
    expect(getDateFnsLocale('en').code).toBe('en-US');
    expect(getDateFnsLocale('es').code).toBe('es');
  });

  it('falls back to the default locale when missing or unmapped', () => {
    expect(getDateFnsLocale(undefined).code).toBe('en-US');
    expect(getDateFnsLocale('de').code).toBe('en-US');
  });
});

describe('getLocaleDirection', () => {
  it('returns ltr for every supported locale', () => {
    expect(getLocaleDirection('en')).toBe('ltr');
    expect(getLocaleDirection('es')).toBe('ltr');
    expect(getLocaleDirection(undefined)).toBe('ltr');
  });
});

describe('mapBrowserLanguageToSupported', () => {
  it('strips the country suffix to a supported prefix', () => {
    expect(mapBrowserLanguageToSupported('es-AR')).toBe('es');
    expect(mapBrowserLanguageToSupported('en-US')).toBe('en');
    expect(mapBrowserLanguageToSupported('ES')).toBe('es');
  });

  it('falls back to the default for unsupported languages', () => {
    expect(mapBrowserLanguageToSupported('pt-BR')).toBe('en');
    expect(mapBrowserLanguageToSupported('de')).toBe('en');
  });
});

describe('detectBrowserLanguage', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('maps the browser language to a supported locale', () => {
    vi.stubGlobal('navigator', { language: 'es-AR' });
    expect(detectBrowserLanguage()).toBe('es');
    vi.stubGlobal('navigator', { language: 'pt-BR' });
    expect(detectBrowserLanguage()).toBe('en');
  });

  it('falls back to the default locale when navigator is unavailable', () => {
    vi.stubGlobal('navigator', undefined);
    expect(detectBrowserLanguage()).toBe(DEFAULT_LOCALE);
  });
});
