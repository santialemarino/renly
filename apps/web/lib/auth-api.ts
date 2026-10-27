// The auth calls the BROWSER makes to the API itself (the signup, forgot, reset and verify forms),
// plus the types and errors both sides share. The calls this server makes on a visitor's behalf
// (login, refresh, signup context) live in lib/auth-api-server.ts, behind serverApiFetch.

import { parseApiError, type ApiError } from '@/lib/i18n/api-errors';

const apiUrl = process.env.NEXT_PUBLIC_API_URL as string;

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
  // Raw invite token from the emailed link; required by the API in invite-only mode (SIGNUP_MODE).
  inviteToken?: string;
  // Active UI locale, so the API localizes the verification email and seeds the language preference.
  language?: string;
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

// Thrown when the API rate-limits an auth request (429). Carries the parsed error — its
// `rate_limited` code and the Retry-After wait — so the form shows the localized "too many attempts,
// try again in N minutes" rather than reading the refusal as a wrong password or a server error.
export class RateLimitedError extends Error {
  constructor(readonly apiError: ApiError) {
    super('rate_limited');
    this.name = 'RateLimitedError';
  }
}

// Throws RateLimitedError for a rate-limited response; any other response passes through.
export async function throwIfRateLimited(res: Response): Promise<void> {
  if (res.status === 429) throw new RateLimitedError(await parseApiError(res));
}

export type SignupMode = 'invite' | 'open';

export interface SignupContext {
  mode: SignupMode;
  // The address the invite is bound to (lock the form to it); null in open mode or for an invalid token.
  invitedEmail: string | null;
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
      language: data.language,
    }),
  });
  await throwIfRateLimited(res);
  if (res.status === 403) throw new InviteInvalidError();
  if (res.status === 400) throw new PasswordRejectedError();
  if (!res.ok) throw new Error(await errorDetail(res, 'register_failed'));
}

// Requests a password-reset email (AUTH-2). Uniform 202 regardless of whether the address exists.
export async function forgotPasswordRequest(email: string): Promise<void> {
  const res = await fetch(`${apiUrl}/auth/forgot-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  await throwIfRateLimited(res);
  if (!res.ok) throw new Error(await errorDetail(res, 'forgot_failed'));
}

// Sets a new password from a reset token (AUTH-2). Throws the API detail on an invalid/expired token.
export async function resetPasswordRequest(token: string, password: string): Promise<void> {
  const res = await fetch(`${apiUrl}/auth/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, password }),
  });
  await throwIfRateLimited(res);
  if (!res.ok) throw new Error(await errorDetail(res, 'reset_failed'));
}

// (Re)sends an email-verification link (AUTH-1). Uniform 202 regardless of account state.
export async function requestVerificationEmail(email: string): Promise<void> {
  const res = await fetch(`${apiUrl}/auth/verify-email/request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  await throwIfRateLimited(res);
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
