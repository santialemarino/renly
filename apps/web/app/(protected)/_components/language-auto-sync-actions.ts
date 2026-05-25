'use server';

import { revalidatePath } from 'next/cache';
import { cookies } from 'next/headers';

import { LOCALE_COOKIE } from '@/config/constants';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { LANGUAGE_MODE_AUTO } from '@/lib/constants/languages';

// One-year max-age — the cookie is the SSR locale signal; it should outlive sessions.
const LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

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
