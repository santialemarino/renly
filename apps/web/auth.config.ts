import type { NextAuthConfig, Session, User } from 'next-auth';
import type { JWT } from 'next-auth/jwt';
import Credentials from 'next-auth/providers/credentials';

import { AUTH_ROUTES, LOGIN_ROUTE } from '@/config/routes';
import { loginRequest, meRequest } from '@/lib/auth-api';

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
      },
      authorize: async (credentials) => {
        const email = credentials?.email as string;
        const password = credentials?.password as string;
        if (!email || !password) return null;

        const tokens = await loginRequest(email, password);
        if (!tokens) return null;

        const me = await meRequest(tokens.access_token);
        if (!me) return null;

        return {
          id: String(me.uid),
          email: me.email,
          name: me.name,
          accessToken: tokens.access_token,
          expiresIn: tokens.expires_in,
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

      const isAuthPage = AUTH_ROUTES.some(
        (page) => pathname === page || pathname.startsWith(page + '/'),
      );

      if (isAuthPage) return true;

      if (!isLoggedIn || hasError) {
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
        return token;
      }

      // Token still valid
      if (
        token.accessToken &&
        typeof token.accessTokenExpires === 'number' &&
        Date.now() < token.accessTokenExpires
      ) {
        return token;
      }

      // Expired, force re-login
      return { ...token, error: 'SessionExpired' as const };
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
