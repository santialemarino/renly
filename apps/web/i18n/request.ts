import { cookies, headers } from 'next/headers';
import { getRequestConfig } from 'next-intl/server';

import { isValidTimezone, TIMEZONE_COOKIE } from '@/lib/constants/timezones';
import { DEFAULT_LOCALE, LOCALE_COOKIE, SUPPORTED_LOCALES } from '@/lib/i18n/locales';

function getLocaleFromCookie(cookieStore: Awaited<ReturnType<typeof cookies>>): string | null {
  const stored = cookieStore.get(LOCALE_COOKIE)?.value;
  if (!stored) return null;
  if (SUPPORTED_LOCALES.includes(stored as (typeof SUPPORTED_LOCALES)[number])) {
    return stored;
  }
  return null;
}

function getLocaleFromHeader(headersList: Headers): string | null {
  const acceptLanguage = headersList.get('accept-language');
  if (!acceptLanguage) return null;

  const languages = acceptLanguage
    .split(',')
    .map((lang) => lang.split(';')[0]?.trim().toLowerCase())
    .filter((lang): lang is string => Boolean(lang));

  for (const lang of languages) {
    if (SUPPORTED_LOCALES.includes(lang as (typeof SUPPORTED_LOCALES)[number])) {
      return lang;
    }
    const langPrefix = lang.split('-')[0];
    if (
      langPrefix &&
      SUPPORTED_LOCALES.includes(langPrefix as (typeof SUPPORTED_LOCALES)[number])
    ) {
      return langPrefix;
    }
  }

  return null;
}

export default getRequestConfig(async () => {
  const [cookieStore, headersList] = await Promise.all([cookies(), headers()]);

  // Cookie (set by saveLocalization + syncBrowserLanguage actions) wins over Accept-Language.
  let locale =
    getLocaleFromCookie(cookieStore) || getLocaleFromHeader(headersList) || DEFAULT_LOCALE;

  if (!SUPPORTED_LOCALES.includes(locale as (typeof SUPPORTED_LOCALES)[number])) {
    locale = DEFAULT_LOCALE;
  }

  // Timezone cookie (set by saveLocalization + syncBrowserTimezone) drives next-intl's timeZone,
  // which the formatters hook reads to render full ISO timestamps in the user's stored zone. When
  // absent or invalid, leave it unset so timestamps fall back to the ambient (browser/server) zone.
  const storedTimezone = cookieStore.get(TIMEZONE_COOKIE)?.value;
  const timeZone = storedTimezone && isValidTimezone(storedTimezone) ? storedTimezone : undefined;

  return {
    locale,
    timeZone,
    messages: (await import(`../translations/${locale}.json`)).default,
  };
});
