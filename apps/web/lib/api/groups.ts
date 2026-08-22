// Server-only types + mappers for shared-money groups — the people entity. Reads go through
// `getGroups()` / `getGroup()`; mutations are server actions in `app/(protected)/shared/group-actions.ts`.
//
// `getInvitePreview` is the one function here that is NOT authenticated: it reads a join link before
// the holder is a member (or even logged in), so it goes straight to the API without a token. The link
// itself is the credential.

import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import type { GroupKind, GroupRole } from '@/lib/constants/groups';

const apiUrl = process.env.NEXT_PUBLIC_API_URL as string;

// --- Raw types (API JSON shape, snake_case) ---

interface GroupMemberRaw {
  id: number;
  display_name: string;
  role: GroupRole;
  is_active: boolean;
  is_linked: boolean;
  is_self: boolean;
  has_pending_invite: boolean;
  joined_at: string | null;
  created_at: string;
  updated_at: string;
}

interface GroupRaw {
  id: number;
  name: string;
  kind: GroupKind;
  my_role: GroupRole;
  active_member_count: number;
  created_at: string;
  updated_at: string;
  members: GroupMemberRaw[];
}

interface GroupInvitePreviewRaw {
  group_name: string;
  group_kind: GroupKind;
  member_display_name: string;
  invited_by_name: string | null;
  expires_at: string;
}

// --- Frontend types (camelCase) ---

export interface GroupMember {
  id: number;
  displayName: string;
  role: GroupRole;
  isActive: boolean;
  // Whether a Renly account holds this seat; false is a name-only placeholder.
  isLinked: boolean;
  isSelf: boolean;
  hasPendingInvite: boolean;
  joinedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface Group {
  id: number;
  name: string;
  kind: GroupKind;
  myRole: GroupRole;
  activeMemberCount: number;
  createdAt: string;
  updatedAt: string;
  members: GroupMember[];
}

export interface GroupInvitePreview {
  groupName: string;
  groupKind: GroupKind;
  memberDisplayName: string;
  invitedByName: string | null;
  expiresAt: string;
}

// --- Mappers ---

function mapGroupMember(raw: GroupMemberRaw): GroupMember {
  return {
    id: raw.id,
    displayName: raw.display_name,
    role: raw.role,
    isActive: raw.is_active,
    isLinked: raw.is_linked,
    isSelf: raw.is_self,
    hasPendingInvite: raw.has_pending_invite,
    joinedAt: raw.joined_at,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function mapGroup(raw: GroupRaw): Group {
  return {
    id: raw.id,
    name: raw.name,
    kind: raw.kind,
    myRole: raw.my_role,
    activeMemberCount: raw.active_member_count,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    members: raw.members.map(mapGroupMember),
  };
}

function mapInvitePreview(raw: GroupInvitePreviewRaw): GroupInvitePreview {
  return {
    groupName: raw.group_name,
    groupKind: raw.group_kind,
    memberDisplayName: raw.member_display_name,
    invitedByName: raw.invited_by_name,
    expiresAt: raw.expires_at,
  };
}

// --- API functions ---

export async function getGroups(): Promise<Group[]> {
  const res = await authenticatedFetch('/groups', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch groups');
  const raw: GroupRaw[] = await res.json();
  return raw.map(mapGroup);
}

// Returns null for a group that does not exist OR that the user is not a member of — the API answers
// 404 for both, and the page renders notFound() either way, so an id cannot be probed.
export async function getGroup(groupId: number): Promise<Group | null> {
  const res = await authenticatedFetch(`/groups/${groupId}`, { method: 'GET' });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Failed to fetch group');
  return mapGroup(await res.json());
}

// Unauthenticated read of a join link. Returns null for a token that is unknown, already claimed or
// expired — one answer for all three, matching the API, so a token cannot be probed either.
export async function getInvitePreview(token: string): Promise<GroupInvitePreview | null> {
  try {
    const res = await fetch(`${apiUrl}/group-invites/${encodeURIComponent(token)}`, {
      cache: 'no-store',
    });
    if (!res.ok) return null;
    return mapInvitePreview(await res.json());
  } catch {
    return null;
  }
}
