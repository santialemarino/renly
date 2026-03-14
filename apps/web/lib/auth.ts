import { auth } from '@/auth';

/**
 * Server-side helper to get the current authenticated session.
 * Use in Server Components and Server Actions.
 */
export const getSession = async () => {
  return auth();
};

/**
 * Server-side helper to get the access token for API calls.
 */
export const getAccessToken = async (): Promise<string | null> => {
  const session = await auth();
  return session?.user?.accessToken ?? null;
};
