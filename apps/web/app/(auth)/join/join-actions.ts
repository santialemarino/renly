'use server';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { isRefusal, localizedApiError } from '@/lib/i18n/api-errors-server';

/*
 * Claims the seat a join link points at, for the logged-in account. Authenticated (unlike the preview
 * read on the page itself) because claiming needs to know WHO is claiming — the token says which seat,
 * the session says whose it becomes.
 *
 * Returns the joined group so the card can send the user straight to its hub, and returns a refusal as
 * DATA rather than throwing: the two that actually happen — the link died while they were logging in,
 * or they already hold a seat in that group — both have something specific to say.
 */
export type JoinGroupResult =
  | { ok: true; groupId: number; groupName: string }
  | { ok: false; reason: string };

export async function acceptGroupInvite(token: string): Promise<JoinGroupResult> {
  const res = await authenticatedFetch(`/group-invites/${encodeURIComponent(token)}/accept`, {
    method: 'POST',
  });
  if (!res.ok) {
    const reason = isRefusal(res) ? await localizedApiError(res) : null;
    if (reason) return { ok: false, reason };
    throw new Error('Failed to accept group invite');
  }
  const raw: { group_id: number; group_name: string } = await res.json();
  return { ok: true, groupId: raw.group_id, groupName: raw.group_name };
}
