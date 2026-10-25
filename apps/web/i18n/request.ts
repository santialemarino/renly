import { cookies, headers } from 'next/headers';
import { getRequestConfig } from 'next-intl/server';

import { getSettings, type SettingsData } from '@/lib/api/settings';
import { getSession, isAuthenticatedSession } from '@/lib/auth';
import { pinnedTimezone, resolveTimezone, TIMEZONE_COOKIE } from '@/lib/constants/timezones';
import { withErrorBoundaryMessages } from '@/lib/i18n/error-boundary-messages';
import { LOCALE_COOKIE, pinnedLocale, resolveLocale } from '@/lib/i18n/locales';

// The Accept-Language header as an ordered list of language tags, quality values dropped.
function parseAcceptLanguage(headersList: Headers): string[] {
  const acceptLanguage = headersList.get('accept-language');
  if (!acceptLanguage) return [];

  return acceptLanguage
    .split(',')
    .map((lang) => lang.split(';')[0]?.trim().toLowerCase())
    .filter((lang): lang is string => Boolean(lang));
}

// The signed-in user's stored settings, or null for a visitor or when they cannot be read. Both reads
// are request-memoized, so on a protected page this shares the layout's session decode and /settings call.
async function getStoredSettings(): Promise<SettingsData | null> {
  const session = await getSession();
  if (!isAuthenticatedSession(session)) return null;
  return getSettings().catch(() => null);
}

export default getRequestConfig(async () => {
  const [cookieStore, headersList, settings] = await Promise.all([
    cookies(),
    headers(),
    getStoredSettings(),
  ]);

  // A manual language pinned in the user's settings wins, then the cookie (set by saveLocalization,
  // syncBrowserLanguage and seedLocaleCookie), then Accept-Language. See resolveLocale.
  const locale = resolveLocale(
    cookieStore.get(LOCALE_COOKIE)?.value,
    parseAcceptLanguage(headersList),
    pinnedLocale(settings?.language, settings?.languageMode),
  );

  // The zone drives next-intl's timeZone, which the formatters hook reads to render full ISO
  // timestamps in the user's zone: a pinned manual zone, else the cookie (set by saveLocalization,
  // syncBrowserTimezone and seedTimezoneCookie). When neither resolves, it stays unset so timestamps
  // fall back to the ambient (browser/server) zone.
  const timeZone = resolveTimezone(
    cookieStore.get(TIMEZONE_COOKIE)?.value,
    pinnedTimezone(settings?.timezone, settings?.timezoneMode),
  );

  return {
    locale,
    timeZone,
    messages: withErrorBoundaryMessages(
      (await import(`../translations/${locale}.json`)).default,
      locale,
    ),
  };
});
