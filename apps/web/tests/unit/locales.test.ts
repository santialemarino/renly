import { readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  DEFAULT_LOCALE,
  detectBrowserLanguage,
  getDateFnsLocale,
  getLocaleDirection,
  getLocaleTag,
  LANGUAGE_OPTIONS,
  mapBrowserLanguageToSupported,
  pinnedLocale,
  resolveLocale,
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

/*
 * The registry and the message files are two transcriptions of one fact. `i18n/request.ts` loads
 * `translations/<code>.json` with a dynamic import for whichever supported locale a request resolves to,
 * so a registry entry without its file is a 500 on every page in that one language — the default locale
 * keeps working and nothing at build time notices. A file without a registry entry is copy no user can
 * reach. Compared both ways, for the main files and for the error-boundary files `global-error.tsx` imports.
 */
describe('locale registry vs translation files', () => {
  const translations = resolve(dirname(fileURLToPath(import.meta.url)), '../../translations');
  const codesIn = (dir: string) =>
    readdirSync(dir)
      .filter((file) => file.endsWith('.json'))
      .map((file) => file.slice(0, -'.json'.length))
      .sort();

  it.each([
    ['translations', translations],
    ['translations/error-boundary', join(translations, 'error-boundary')],
  ])('%s holds exactly one file per supported locale', (_, dir) => {
    expect(codesIn(dir)).toEqual([...SUPPORTED_LOCALES].sort());
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

/*
 * The one rule both the server render (cookie + Accept-Language) and the global error page (cookie +
 * navigator.languages) resolve a locale with, so the two cannot pick differently for one visitor.
 */
describe('resolveLocale', () => {
  it('prefers a supported locale cookie over every language', () => {
    expect(resolveLocale('es', ['en-US', 'en'])).toBe('es');
  });

  it('ignores an unsupported cookie and falls through to the languages', () => {
    expect(resolveLocale('fr', ['es-AR'])).toBe('es');
    expect(resolveLocale(undefined, ['es'])).toBe('es');
  });

  it('takes the first supported language, exactly or by its prefix, in order', () => {
    expect(resolveLocale(null, ['pt-BR', 'es-AR', 'en'])).toBe('es');
    expect(resolveLocale(null, ['ES-ar'])).toBe('es');
    expect(resolveLocale(null, [' en '])).toBe('en');
  });

  it('falls back to the default when nothing resolves', () => {
    expect(resolveLocale(undefined, [])).toBe(DEFAULT_LOCALE);
    expect(resolveLocale('xx', ['pt-BR', 'de'])).toBe(DEFAULT_LOCALE);
  });

  it('puts a pinned language ahead of the cookie and every language', () => {
    expect(resolveLocale('en', ['en-US'], 'es')).toBe('es');
    expect(resolveLocale(undefined, ['en-US'], 'es')).toBe('es');
    expect(resolveLocale('es', ['en-US'], null)).toBe('es');
  });
});

describe('pinnedLocale', () => {
  it('pins only a supported language whose mode is manual', () => {
    expect(pinnedLocale('es', 'manual')).toBe('es');
    expect(pinnedLocale('es', 'auto')).toBeNull();
    expect(pinnedLocale('es', null)).toBeNull();
    expect(pinnedLocale('fr', 'manual')).toBeNull();
    expect(pinnedLocale(null, 'manual')).toBeNull();
  });
});
