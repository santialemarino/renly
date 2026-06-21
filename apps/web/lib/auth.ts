import { cache } from 'react';
import type { Session } from 'next-auth';

import { auth } from '@/auth';

/**
 * Server-side helper to get the current authenticated session. Memoized per request so multiple
 * callers in one render (e.g. a page and the layout's header both reading the session) share a
 * single decode instead of re-decoding the JWT each time.
 * Use in Server Components and Server Actions.
 */
export const getSession = cache(async () => {
  return auth();
});

/**
 * Server-side helper to get the access token for API calls.
 */
export const getAccessToken = async (): Promise<string | null> => {
  const session = await getSession();
  return session?.user?.accessToken ?? null;
};

/** Whether a session is usable: it has a user and carries no refresh/session error. */
export const isAuthenticatedSession = (session: Session | null): boolean =>
  !!session?.user && !session.user.error;
