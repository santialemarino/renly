'use server';

import { revalidatePath } from 'next/cache';
import { cookies } from 'next/headers';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import {
  isSupportedLocale,
  LANGUAGE_MODE_AUTO,
  LOCALE_COOKIE,
  LOCALE_COOKIE_MAX_AGE,
} from '@/lib/i18n/locales';

// Silent PUT of browser-detected language. Called from the layout-level LanguageAutoSync
// effect when mode is 'auto' and the browser language differs from stored. Keeps mode = auto.
// Also writes the NEXT_LOCALE cookie so SSR picks it up on the next render.
// Errors swallowed by caller (next page load retries). Colocated with the only caller
// (LanguageAutoSync) since the action isn't tied to a specific page.
export async function syncBrowserLanguage(language: string): Promise<void> {
  const res = await authenticatedFetch('/settings', {
    method: 'PUT',
    body: { language, language_mode: LANGUAGE_MODE_AUTO },
  });
  if (!res.ok) throw new Error('Failed to sync browser language');
  const cookieStore = await cookies();
  cookieStore.set(LOCALE_COOKIE, language, {
    maxAge: LOCALE_COOKIE_MAX_AGE,
    path: '/',
    sameSite: 'lax',
  });
  revalidatePath('/', 'layout');
}

// Writes the NEXT_LOCALE cookie only — no settings PUT, no revalidation. Called at login
// (seedLocalizationCookies), and from LanguageAutoSync when the user's language is pinned ('manual')
// and this browser's cookie is absent or names another locale (the pin changed on another device, or
// the cookie was cleared). A document already renders in the pinned language (i18n/request.ts reads the
// pin); this brings the cookie — which link prefetches, client-side navigations and the root error
// boundary render from — into agreement. An unsupported value is ignored.
export async function seedLocaleCookie(language: string): Promise<void> {
  if (!isSupportedLocale(language)) return;
  const cookieStore = await cookies();
  cookieStore.set(LOCALE_COOKIE, language, {
    maxAge: LOCALE_COOKIE_MAX_AGE,
    path: '/',
    sameSite: 'lax',
  });
}
