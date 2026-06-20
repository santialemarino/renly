import 'next-auth';
import 'next-auth/jwt';

declare module 'next-auth' {
  interface Session {
    user: {
      id: string;
      email: string;
      name: string;
      accessToken: string;
      expiresIn: number;
      error?: string;
    };
  }

  interface User {
    id: string;
    email: string;
    name: string;
    accessToken: string;
    expiresIn: number;
    refreshToken: string;
    refreshExpiresIn: number;
  }
}

declare module 'next-auth/jwt' {
  interface JWT {
    uid: string;
    email: string;
    name: string;
    accessToken: string;
    accessTokenExpires: number;
    // Refresh token (AUTH-7) — kept inside the encrypted NextAuth JWT, never exposed to the session.
    // Optional: absent on JWTs minted before AUTH-7, and cleared once a refresh fails terminally.
    refreshToken?: string;
    refreshTokenExpires?: number;
    error?: string;
  }
}

export {};
