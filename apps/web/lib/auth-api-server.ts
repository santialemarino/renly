import 'server-only';

import { throwIfRateLimited, type SignupContext, type SignupMode } from '@/lib/auth-api';
import { serverApiFetch } from '@/lib/server-api-fetch';

// The auth calls this server makes to the API on a visitor's behalf — Auth.js's sign-in and token
// refresh, the signup context the pages render from. Every one goes through serverApiFetch, so the
// API rate-limits it by the visitor rather than by this server.

export interface MeResponse {
  uid: number;
  email: string;
  name: string;
  emailVerified: boolean;
  isAdmin: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string;
  refresh_expires_in: number;
}

// Fetches the signup context: whether registration is invite-only and, for a valid invite token, the
// address to lock the form to. Falls back to the safe default (invite-only, no email) when the API is
// unreachable, so the public surface never implies open registration on an outage.
export async function getSignupContext(inviteToken?: string): Promise<SignupContext> {
  try {
    const query = inviteToken ? `?invite=${encodeURIComponent(inviteToken)}` : '';
    const res = await serverApiFetch(`/auth/signup-context${query}`, { cache: 'no-store' });
    if (!res.ok) return { mode: 'invite', invitedEmail: null };
    const raw = (await res.json()) as { signup_mode: SignupMode; invited_email: string | null };
    return { mode: raw.signup_mode, invitedEmail: raw.invited_email };
  } catch {
    return { mode: 'invite', invitedEmail: null };
  }
}

// Logs in (AUTH-7). `rememberMe` controls the refresh token's lifetime — a longer, persistent
// session when checked. Returns the access + refresh tokens, null for any other non-OK status, and
// throws RateLimitedError on a 429 so it is not mistaken for wrong credentials.
export async function loginRequest(
  email: string,
  password: string,
  rememberMe: boolean,
): Promise<TokenResponse | null> {
  const res = await serverApiFetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, remember_me: rememberMe }),
  });
  await throwIfRateLimited(res);
  if (!res.ok) return null;
  return res.json() as Promise<TokenResponse>;
}

// Discriminates refresh outcomes so only a definitive rejection kills the session: 'expired' means
// the API said 401 (token dead — re-login); 'transient' means the API was unreachable or errored
// (network blip, 5xx) — keep the refresh token and retry on the next jwt() pass.
export type RefreshResult =
  | { kind: 'ok'; tokens: TokenResponse }
  | { kind: 'expired' }
  | { kind: 'transient' };

// Exchanges a refresh token for a fresh access token and a rotated refresh token (AUTH-7). Only an
// HTTP 401 is terminal; anything else is a transient failure that must not log the user out.
export async function refreshRequest(refreshToken: string): Promise<RefreshResult> {
  let res: Response;
  try {
    res = await serverApiFetch('/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } catch {
    return { kind: 'transient' };
  }
  if (res.status === 401) return { kind: 'expired' };
  if (!res.ok) return { kind: 'transient' };
  return { kind: 'ok', tokens: (await res.json()) as TokenResponse };
}

export async function meRequest(accessToken: string): Promise<MeResponse | null> {
  const res = await serverApiFetch('/auth/me', {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: 'no-store',
  });
  if (!res.ok) return null;
  const raw = (await res.json()) as {
    uid: number;
    email: string;
    name: string;
    email_verified: boolean;
    is_admin: boolean;
  };
  return {
    uid: raw.uid,
    email: raw.email,
    name: raw.name,
    emailVerified: raw.email_verified,
    isAdmin: raw.is_admin,
  };
}

export async function logoutRequest(accessToken: string): Promise<void> {
  await serverApiFetch('/auth/logout', {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}
