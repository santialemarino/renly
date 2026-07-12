const apiUrl = process.env.NEXT_PUBLIC_API_URL as string;

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
  // Raw invite token from the emailed link; required by the API in invite-only mode (SIGNUP_MODE).
  inviteToken?: string;
}

// Thrown when the API rejects a password (the only 400 from register/reset): too weak or breached.
export class PasswordRejectedError extends Error {
  constructor() {
    super('password_rejected');
    this.name = 'PasswordRejectedError';
  }
}

// Thrown when the API rejects an invite at registration (invite-only mode, 403): the token is
// missing, unknown, expired, already used, or doesn't match the email.
export class InviteInvalidError extends Error {
  constructor() {
    super('invite_invalid');
    this.name = 'InviteInvalidError';
  }
}

export type SignupMode = 'invite' | 'open';

export interface SignupContext {
  mode: SignupMode;
  // The address the invite is bound to (lock the form to it); null in open mode or for an invalid token.
  invitedEmail: string | null;
}

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

// Reads the API's `detail` message from an error response, falling back to a generic label.
async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string };
    return body.detail || fallback;
  } catch {
    return fallback;
  }
}

/*
 * Registers an account (AUTH-5). The API always returns a uniform 202 — a new address is emailed a
 * verification link, an existing one a "you already have an account" notice — so this never reveals
 * whether the email is taken. A breached password (400) surfaces its message; the caller shows a
 * "check your email" screen on success.
 */
export async function registerRequest(data: RegisterPayload): Promise<void> {
  const res = await fetch(`${apiUrl}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: data.name,
      email: data.email,
      password: data.password,
      invite_token: data.inviteToken,
    }),
  });
  if (res.status === 403) throw new InviteInvalidError();
  if (res.status === 400) throw new PasswordRejectedError();
  if (!res.ok) throw new Error(await errorDetail(res, 'register_failed'));
}

// Fetches the signup context: whether registration is invite-only and, for a valid invite token, the
// address to lock the form to. Falls back to the safe default (invite-only, no email) when the API is
// unreachable, so the public surface never implies open registration on an outage.
export async function getSignupContext(inviteToken?: string): Promise<SignupContext> {
  try {
    const query = inviteToken ? `?invite=${encodeURIComponent(inviteToken)}` : '';
    const res = await fetch(`${apiUrl}/auth/signup-context${query}`, { cache: 'no-store' });
    if (!res.ok) return { mode: 'invite', invitedEmail: null };
    const raw = (await res.json()) as { signup_mode: SignupMode; invited_email: string | null };
    return { mode: raw.signup_mode, invitedEmail: raw.invited_email };
  } catch {
    return { mode: 'invite', invitedEmail: null };
  }
}

// Logs in (AUTH-7). `rememberMe` controls the refresh token's lifetime — a longer, persistent
// session when checked. Returns the access + refresh tokens, or null for any non-OK status.
export async function loginRequest(
  email: string,
  password: string,
  rememberMe: boolean,
): Promise<TokenResponse | null> {
  const res = await fetch(`${apiUrl}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, remember_me: rememberMe }),
  });
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
    res = await fetch(`${apiUrl}/auth/refresh`, {
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
  const res = await fetch(`${apiUrl}/auth/me`, {
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
  await fetch(`${apiUrl}/auth/logout`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

// Requests a password-reset email (AUTH-2). Uniform 202 regardless of whether the address exists.
export async function forgotPasswordRequest(email: string): Promise<void> {
  const res = await fetch(`${apiUrl}/auth/forgot-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'forgot_failed'));
}

// Sets a new password from a reset token (AUTH-2). Throws the API detail on an invalid/expired token.
export async function resetPasswordRequest(token: string, password: string): Promise<void> {
  const res = await fetch(`${apiUrl}/auth/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, password }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'reset_failed'));
}

// (Re)sends an email-verification link (AUTH-1). Uniform 202 regardless of account state.
export async function requestVerificationEmail(email: string): Promise<void> {
  const res = await fetch(`${apiUrl}/auth/verify-email/request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'verify_request_failed'));
}

export type ConfirmEmailKind = 'email_verification' | 'email_change';

// Confirms a verification or email-change token (AUTH-1/8). Returns which flow completed so the
// landing page can tailor its copy; throws the API detail on an invalid/expired token.
export async function confirmEmailToken(token: string): Promise<ConfirmEmailKind> {
  const res = await fetch(`${apiUrl}/auth/verify-email/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, 'confirm_failed'));
  const body = (await res.json()) as { token_type: ConfirmEmailKind };
  return body.token_type;
}
