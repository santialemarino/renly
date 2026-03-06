'use server';

import NextAuth from 'next-auth';

import { logoutRequest } from '@/lib/auth-api';
import { authConfig } from './auth.config';

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
};
