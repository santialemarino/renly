'use server';

import { revalidatePath } from 'next/cache';

import { ROUTES } from '@/config/routes';
import { mapInvite, type Invite } from '@/lib/api/invites';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { rateLimitedMessage } from '@/lib/i18n/api-errors-server';

// 'taken' = the email already has an account (409); 'error' = anything else non-OK, with a message
// worth showing (a rate limit) or null for the generic one.
export type CreateInviteResult =
  | { status: 'ok'; invite: Invite }
  | { status: 'taken' }
  | { status: 'error'; message: string | null };

// A resend's outcome: the re-armed invite, or an error as in CreateInviteResult.
export type ResendInviteResult =
  | { status: 'ok'; invite: Invite }
  | { status: 'error'; message: string | null };

export async function createInvite(email: string): Promise<CreateInviteResult> {
  const res = await authenticatedFetch('/admin/invites', { method: 'POST', body: { email } });
  if (res.status === 409) return { status: 'taken' };
  if (!res.ok) return { status: 'error', message: await rateLimitedMessage(res) };
  revalidatePath(ROUTES.admin, 'page');
  return { status: 'ok', invite: mapInvite(await res.json()) };
}

export async function resendInvite(id: number): Promise<ResendInviteResult> {
  const res = await authenticatedFetch(`/admin/invites/${id}/resend`, { method: 'POST' });
  if (!res.ok) return { status: 'error', message: await rateLimitedMessage(res) };
  revalidatePath(ROUTES.admin, 'page');
  return { status: 'ok', invite: mapInvite(await res.json()) };
}

export async function revokeInvite(id: number): Promise<Invite | null> {
  const res = await authenticatedFetch(`/admin/invites/${id}/revoke`, { method: 'POST' });
  if (!res.ok) return null;
  revalidatePath(ROUTES.admin, 'page');
  return mapInvite(await res.json());
}
