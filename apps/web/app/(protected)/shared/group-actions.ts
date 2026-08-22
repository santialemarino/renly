'use server';

import type {
  GroupFormValues,
  GroupInviteFormValues,
  GroupMemberFormValues,
} from '@/app/(protected)/shared/group-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { isRefusal, localizedApiError } from '@/lib/i18n/api-errors-server';

/*
 * Every mutation returns its refusal as DATA rather than throwing, which is what
 * `useEntityFormDialog.submitWithLifecycle` understands: the Server Action boundary strips prototype
 * chains, so a thrown class instance reaches the client as a plain `Error` with its message gone.
 *
 * The group refusals worth showing are the ones a stale page produces — you were demoted in another
 * tab (403 group_admin_required), you are the last admin (409 group_last_admin), someone claimed the
 * seat first (409 group_membership_exists), or the link died (400 invalid_token). None of them is a
 * crash, and all of them have something specific to say.
 */
export type GroupMutationResult = { ok: true } | { ok: false; conflictDetail: string };

// Turns a failed response into either a surfaced refusal or a throw. One helper so every action below
// classifies failures identically — the alternative is eight copies that drift.
async function toResult(res: Response, failureMessage: string): Promise<GroupMutationResult> {
  if (res.ok) return { ok: true };
  const detail = isRefusal(res) ? await localizedApiError(res) : null;
  if (detail) return { ok: false, conflictDetail: detail };
  throw new Error(failureMessage);
}

export async function createGroup(values: GroupFormValues): Promise<GroupMutationResult> {
  const res = await authenticatedFetch('/groups', {
    method: 'POST',
    body: {
      name: values.name,
      kind: values.kind,
      display_name: values.displayName || null,
    },
  });
  return toResult(res, 'Failed to create group');
}

export async function updateGroup(
  id: number,
  values: GroupFormValues,
): Promise<GroupMutationResult> {
  // displayName is a property of the creator's SEAT, not of the group, so editing a group never
  // sends it — the seat is renamed from the roster like any other member's.
  const res = await authenticatedFetch(`/groups/${id}`, {
    method: 'PUT',
    body: { name: values.name, kind: values.kind },
  });
  return toResult(res, 'Failed to update group');
}

export async function deleteGroup(id: number): Promise<GroupMutationResult> {
  const res = await authenticatedFetch(`/groups/${id}`, { method: 'DELETE' });
  return toResult(res, 'Failed to delete group');
}

export async function addGroupMember(
  groupId: number,
  values: GroupMemberFormValues,
): Promise<GroupMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/members`, {
    method: 'POST',
    body: { display_name: values.displayName, role: values.role },
  });
  return toResult(res, 'Failed to add group member');
}

export async function updateGroupMember(
  groupId: number,
  memberId: number,
  values: GroupMemberFormValues,
): Promise<GroupMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/members/${memberId}`, {
    method: 'PUT',
    body: { display_name: values.displayName, role: values.role },
  });
  return toResult(res, 'Failed to update group member');
}

// Brings a former member back. Separate from updateGroupMember because it is a different intent with a
// different confirmation, and sending is_active from the edit form would let a rename silently
// reactivate someone.
export async function reactivateGroupMember(
  groupId: number,
  memberId: number,
): Promise<GroupMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/members/${memberId}`, {
    method: 'PUT',
    body: { is_active: true },
  });
  return toResult(res, 'Failed to reactivate group member');
}

// Deactivates a seat (and drops its pending invite). Also the "leave group" action: the API lets a
// member remove their own seat without being an admin.
export async function removeGroupMember(
  groupId: number,
  memberId: number,
): Promise<GroupMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/members/${memberId}`, {
    method: 'DELETE',
  });
  return toResult(res, 'Failed to remove group member');
}

/*
 * Creates or rotates a seat's invite. Returns the link on success because it exists ONLY in this
 * response — nothing stores the raw token, so the dialog shows it once and a lost link is replaced by
 * calling this again (which also kills the previous one).
 */
export type GroupInviteResult =
  | { ok: true; inviteUrl: string; email: string | null; expiresAt: string }
  | { ok: false; conflictDetail: string };

export async function createGroupInvite(
  groupId: number,
  memberId: number,
  values: GroupInviteFormValues,
): Promise<GroupInviteResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/members/${memberId}/invite`, {
    method: 'POST',
    body: { email: values.email || null },
  });
  if (!res.ok) {
    const detail = isRefusal(res) ? await localizedApiError(res) : null;
    if (detail) return { ok: false, conflictDetail: detail };
    throw new Error('Failed to create group invite');
  }
  const raw: { invite_url: string; email: string | null; expires_at: string } = await res.json();
  return { ok: true, inviteUrl: raw.invite_url, email: raw.email, expiresAt: raw.expires_at };
}

export async function revokeGroupInvite(
  groupId: number,
  memberId: number,
): Promise<GroupMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/members/${memberId}/invite`, {
    method: 'DELETE',
  });
  return toResult(res, 'Failed to revoke group invite');
}
