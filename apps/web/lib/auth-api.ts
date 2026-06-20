const apiUrl = process.env.NEXT_PUBLIC_API_URL as string;

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
}

// Thrown when the API rejects a password (the only 400 from register/reset): too weak or breached.
export class PasswordRejectedError extends Error {
  constructor() {
    super('password_rejected');
    this.name = 'PasswordRejectedError';
  }
}

export interface MeResponse {
  uid: number;
  email: string;
  name: string;
  emailVerified: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
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
    body: JSON.stringify(data),
  });
  if (res.status === 400) throw new PasswordRejectedError();
  if (!res.ok) throw new Error(await errorDetail(res, 'register_failed'));
}

export async function loginRequest(email: string, password: string): Promise<TokenResponse | null> {
  const res = await fetch(`${apiUrl}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) return null;
  return res.json() as Promise<TokenResponse>;
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
  };
  return { uid: raw.uid, email: raw.email, name: raw.name, emailVerified: raw.email_verified };
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
