import { cookies, headers } from 'next/headers';
import { getRequestConfig } from 'next-intl/server';

import { isValidTimezone, TIMEZONE_COOKIE } from '@/lib/constants/timezones';
import { LOCALE_COOKIE, resolveLocale } from '@/lib/i18n/locales';

// The Accept-Language header as an ordered list of language tags, quality values dropped.
function parseAcceptLanguage(headersList: Headers): string[] {
  const acceptLanguage = headersList.get('accept-language');
  if (!acceptLanguage) return [];

  return acceptLanguage
    .split(',')
    .map((lang) => lang.split(';')[0]?.trim().toLowerCase())
    .filter((lang): lang is string => Boolean(lang));
}

export default getRequestConfig(async () => {
  const [cookieStore, headersList] = await Promise.all([cookies(), headers()]);

  // Cookie (set by saveLocalization + syncBrowserLanguage actions) wins over Accept-Language.
  const locale = resolveLocale(
    cookieStore.get(LOCALE_COOKIE)?.value,
    parseAcceptLanguage(headersList),
  );

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
