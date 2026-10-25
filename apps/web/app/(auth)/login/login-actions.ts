'use server';

import { seedLocaleCookie } from '@/app/(protected)/_components/language-auto-sync-actions';
import { seedTimezoneCookie } from '@/app/(protected)/_components/timezone-auto-sync-actions';
import { getSettings } from '@/lib/api/settings';
import { pinnedTimezone } from '@/lib/constants/timezones';
import { pinnedLocale } from '@/lib/i18n/locales';

/*
 * Writes the just-signed-in user's pinned ('manual') language and zone into this browser's cookies,
 * before the first signed-in document loads. Only a document load reads the pin from the settings
 * (i18n/request.ts); the link prefetches and client-side navigations that follow it render from the
 * cookies, so they must already hold the pin — logout dropped the locale cookie, and a visitor's cookie
 * may name another language. 'auto' writes nothing: those follow the browser as before.
 */
export async function seedLocalizationCookies(): Promise<void> {
  const settings = await getSettings();
  const locale = pinnedLocale(settings.language, settings.languageMode);
  const timezone = pinnedTimezone(settings.timezone, settings.timezoneMode);
  await Promise.all([locale && seedLocaleCookie(locale), timezone && seedTimezoneCookie(timezone)]);
}
