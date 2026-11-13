import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// The signed-in user as the API has them NOW. Read here rather than from the session, whose copy of
// the name is the one from sign-in and goes stale the moment the user renames themselves.
export interface CurrentUser {
  name: string;
  email: string;
}

export async function getCurrentUser(): Promise<CurrentUser> {
  const res = await authenticatedFetch('/auth/me', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch the current user');
  const raw = (await res.json()) as { name: string; email: string };
  return { name: raw.name, email: raw.email };
}

// --- Groups using the account name ---

interface GroupUsingAccountNameRaw {
  id: number;
  name: string;
}

interface GroupsUsingAccountNameRaw {
  groups: GroupUsingAccountNameRaw[];
}

// A group where the user's seat is still named exactly as their account: one that renaming the account
// with "also in my groups" would rename them in.
export interface GroupUsingAccountName {
  id: number;
  name: string;
}

function mapGroupUsingAccountName(raw: GroupUsingAccountNameRaw): GroupUsingAccountName {
  return { id: raw.id, name: raw.name };
}

// The groups that would follow a rename of the account, by group name.
export async function getGroupsUsingAccountName(): Promise<GroupUsingAccountName[]> {
  const res = await authenticatedFetch('/me/name/groups', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch the groups using the account name');
  const raw = (await res.json()) as GroupsUsingAccountNameRaw;
  return raw.groups.map(mapGroupUsingAccountName);
}
