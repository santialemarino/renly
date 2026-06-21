import type { NextAuthConfig, Session, User } from 'next-auth';
import type { JWT } from 'next-auth/jwt';
import Credentials from 'next-auth/providers/credentials';

import { AUTH_ROUTES, LOGIN_ROUTE, PROTECTED_ROUTES, PUBLIC_ROUTES } from '@/config/routes';
import { loginRequest, meRequest, refreshRequest } from '@/lib/auth-api';

// Renew the access token slightly before it expires so a request never races a just-expired token.
const ACCESS_TOKEN_REFRESH_SKEW_MS = 60_000;

// Silently renews the access token using the refresh token (AUTH-7). Returns the token with fresh
// access + rotated refresh values, or marks it errored (SessionExpired) so the user is sent to login
// when there is no usable refresh token or the backend rejects it.
async function refreshAccessToken(token: JWT): Promise<JWT> {
  // Terminal failure: drop the (now useless) refresh token so later jwt() calls short-circuit here
  // instead of firing another doomed /auth/refresh, and flag the session for the login redirect.
  const expired: JWT = {
    ...token,
    refreshToken: undefined,
    refreshTokenExpires: undefined,
    error: 'SessionExpired',
  };

  if (
    !token.refreshToken ||
    (typeof token.refreshTokenExpires === 'number' && Date.now() >= token.refreshTokenExpires)
  ) {
    return expired;
  }

  const refreshed = await refreshRequest(token.refreshToken);
  if (!refreshed) {
    return expired;
  }

  return {
    ...token,
    accessToken: refreshed.access_token,
    accessTokenExpires: Date.now() + refreshed.expires_in * 1000,
    refreshToken: refreshed.refresh_token,
    refreshTokenExpires: Date.now() + refreshed.refresh_expires_in * 1000,
    error: undefined,
  };
}

export const authConfig: NextAuthConfig = {
  pages: {
    signIn: LOGIN_ROUTE,
  },
  providers: [
    Credentials({
      name: 'Credentials',
      credentials: {
        email: { label: 'Email', type: 'email' },
        password: { label: 'Password', type: 'password' },
        rememberMe: { label: 'Remember me', type: 'checkbox' },
      },
      authorize: async (credentials) => {
        const email = credentials?.email as string;
        const password = credentials?.password as string;
        if (!email || !password) return null;
        // signIn serializes credentials, so the boolean arrives as the string 'true'.
        const rememberMe = credentials?.rememberMe === 'true' || credentials?.rememberMe === true;

        const tokens = await loginRequest(email, password, rememberMe);
        if (!tokens) return null;

        const me = await meRequest(tokens.access_token);
        if (!me) return null;

        return {
          id: String(me.uid),
          email: me.email,
          name: me.name,
          accessToken: tokens.access_token,
          expiresIn: tokens.expires_in,
          refreshToken: tokens.refresh_token,
          refreshExpiresIn: tokens.refresh_expires_in,
        };
      },
    }),
  ],
  session: { strategy: 'jwt' },
  callbacks: {
    authorized({ auth, request: { nextUrl } }) {
      const isLoggedIn = !!auth?.user;
      const hasError = (auth?.user as { error?: string } | undefined)?.error;
      const pathname = nextUrl.pathname;

      const matchesRoute = (route: string) =>
        pathname === route || pathname.startsWith(route + '/');

      const isAuthPage = AUTH_ROUTES.some(matchesRoute);

      // Marketing landing + legal pages are reachable without a session; the landing page itself
      // redirects logged-in visitors to the app.
      const isPublicPage = PUBLIC_ROUTES.some(
        (page) => pathname === page || (page !== '/' && pathname.startsWith(page + '/')),
      );

      if (isAuthPage || isPublicPage) return true;

      // Only known protected routes force a login redirect when logged out — unknown paths fall
      // through so Next renders not-found (404) instead of bouncing a mistyped URL to /login. This
      // is the optimistic edge check; the (protected) layout's getSession() is the authoritative
      // guard, so a protected route missing from PROTECTED_ROUTES still can't leak.
      const isProtectedPage = PROTECTED_ROUTES.some(matchesRoute);
      if (isProtectedPage && (!isLoggedIn || hasError)) {
        return Response.redirect(new URL(LOGIN_ROUTE, nextUrl));
      }

      return true;
    },
    async jwt({ token, user }: { token: JWT; user?: User }) {
      if (user) {
        token.uid = user.id as string;
        token.email = user.email as string;
        token.name = user.name as string;
        token.accessToken = user.accessToken;
        token.accessTokenExpires = Date.now() + (user.expiresIn as number) * 1000;
        token.refreshToken = user.refreshToken;
        token.refreshTokenExpires = Date.now() + (user.refreshExpiresIn as number) * 1000;
        return token;
      }

      // Access token still valid — nothing to do.
      if (
        token.accessToken &&
        typeof token.accessTokenExpires === 'number' &&
        Date.now() < token.accessTokenExpires - ACCESS_TOKEN_REFRESH_SKEW_MS
      ) {
        return token;
      }

      // Access token expired (or about to) — silently renew it with the refresh token (AUTH-7).
      return refreshAccessToken(token);
    },
    async session({ session, token }: { session: Session; token: JWT }) {
      const expiresInSeconds = Math.max(
        0,
        Math.floor(((token.accessTokenExpires as number) - Date.now()) / 1000),
      );
      session.user = {
        id: token.uid as string,
        email: (token.email as string) ?? session.user?.email,
        name: (token.name as string) ?? session.user?.name ?? '',
        accessToken: token.accessToken as string,
        expiresIn: expiresInSeconds,
        error: token.error as string | undefined,
      };
      return session;
    },
  },
  trustHost: true,
  secret: process.env.NEXTAUTH_SECRET,
} satisfies NextAuthConfig;
