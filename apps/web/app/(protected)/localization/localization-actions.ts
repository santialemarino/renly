'use server';

import { revalidatePath } from 'next/cache';
import { cookies } from 'next/headers';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { LOCALE_COOKIE, LOCALE_COOKIE_MAX_AGE } from '@/lib/i18n/locales';

interface SaveLocalizationParams {
  timezone: string;
  timezoneMode: string;
  language: string;
  languageMode: string;
}

// Persists the user's IANA timezone + language preference (explicit save from the
// Localization form). Sets the NEXT_LOCALE cookie so SSR picks up the language change
// from the next render. Invalidates the layout so subsequent navigations re-read settings.
export async function saveLocalization(params: SaveLocalizationParams): Promise<void> {
  const res = await authenticatedFetch('/settings', {
    method: 'PUT',
    body: {
      timezone: params.timezone,
      timezone_mode: params.timezoneMode,
      language: params.language,
      language_mode: params.languageMode,
    },
  });
  if (!res.ok) throw new Error('Failed to save localization settings');
  const cookieStore = await cookies();
  cookieStore.set(LOCALE_COOKIE, params.language, {
    maxAge: LOCALE_COOKIE_MAX_AGE,
    path: '/',
    sameSite: 'lax',
  });
  revalidatePath('/', 'layout');
}
