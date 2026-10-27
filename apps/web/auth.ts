'use server';

import { cookies } from 'next/headers';
import NextAuth from 'next-auth';

import { authConfig } from '@/auth.config';
import { logoutRequest } from '@/lib/auth-api-server';
import { LOCALE_COOKIE } from '@/lib/i18n/locales';

export const { auth, signIn, signOut } = NextAuth(authConfig);

/**
 * Hits the backend logout endpoint (invalidates session_epoch) then clears
 * the NextAuth session. Client handles the redirect.
 */
export const userSignOut = async (): Promise<void> => {
  const session = await auth();
  const accessToken = session?.user?.accessToken;
  if (accessToken) {
    await logoutRequest(accessToken);
  }
  await signOut({ redirect: false });
  // Drop the locale cookie so the next (logged-out) visitor falls back to their own browser
  // language instead of inheriting the previous user's. Safe: the user's language is persisted in
  // user_settings — a manual one is written back to the cookie at the next login
  // (seedLocalizationCookies) and read by i18n/request.ts on every document load, an auto one follows
  // the browser as it did before.
  (await cookies()).delete(LOCALE_COOKIE);
};
