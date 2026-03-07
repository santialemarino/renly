const apiUrl = process.env.NEXT_PUBLIC_API_URL as string;

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
}

export class EmailTakenError extends Error {
  constructor() {
    super('email_taken');
    this.name = 'EmailTakenError';
  }
}

export async function registerRequest(data: RegisterPayload): Promise<TokenResponse> {
  const res = await fetch(`${apiUrl}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (res.status === 409) throw new EmailTakenError();
  if (!res.ok) throw new Error('register_failed');
  return res.json() as Promise<TokenResponse>;
}

export interface MeResponse {
  uid: number;
  email: string;
  name: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
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
  return res.json() as Promise<MeResponse>;
}

export async function logoutRequest(accessToken: string): Promise<void> {
  await fetch(`${apiUrl}/auth/logout`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}
