'use server';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { rateLimitedMessage } from '@/lib/i18n/api-errors-server';

// Result of a sensitive account mutation: an `error` code the client maps to a localized message,
// or empty on success. A `rate_limited` error carries its already-localized `message`.
export interface AccountActionResult {
  error?: 'invalid_password' | 'password_rejected' | 'rate_limited' | 'server';
  message?: string;
}

// Changes the password (AUTH-8). 401 = wrong current password, 400 = new password rejected (breached).
export async function changePasswordAction(
  currentPassword: string,
  newPassword: string,
): Promise<AccountActionResult> {
  const res = await authenticatedFetch('/me/change-password', {
    method: 'POST',
    body: { current_password: currentPassword, new_password: newPassword },
  });
  if (res.status === 401) return { error: 'invalid_password' };
  if (res.status === 400) return { error: 'password_rejected' };
  if (!res.ok) return { error: 'server' };
  return {};
}

// Requests an email change (AUTH-8). 401 = wrong password; otherwise a uniform 202 (the new address
// is emailed a confirmation link, or a notice if it's already taken).
export async function changeEmailAction(
  currentPassword: string,
  newEmail: string,
): Promise<AccountActionResult> {
  const res = await authenticatedFetch('/me/change-email', {
    method: 'POST',
    body: { current_password: currentPassword, new_email: newEmail },
  });
  if (res.status === 401) return { error: 'invalid_password' };
  const limited = await rateLimitedMessage(res);
  if (limited) return { error: 'rate_limited', message: limited };
  if (!res.ok) return { error: 'server' };
  return {};
}

// Permanently deletes the account (AUTH-6). 401 = wrong password or confirmation mismatch.
export async function deleteAccountAction(
  password: string,
  confirmation: string,
): Promise<AccountActionResult> {
  const res = await authenticatedFetch('/me', {
    method: 'DELETE',
    body: { password, confirmation },
  });
  if (res.status === 401) return { error: 'invalid_password' };
  if (!res.ok) return { error: 'server' };
  return {};
}
