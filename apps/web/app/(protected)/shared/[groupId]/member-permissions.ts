import type { GroupMember } from '@/lib/api/groups';

/*
 * What a roster row shows and offers, as pure functions over one seat.
 *
 * Extracted from the row component for one reason: these are ORDER-DEPENDENT rules with no other
 * guard. `memberStatus` returns the first thing that applies, and swapping two branches shows a
 * plausible-but-wrong label (a removed member reading as "invited", say) that type-checking cannot
 * see. The action predicates decide which controls render at all — the API is the real gate, so a
 * wrong answer here is a UI bug rather than a hole, but it is still the difference between a member
 * seeing a button that 403s and not seeing it.
 *
 * These say nothing about permission to READ. Every member sees the identical roster; only the
 * controls differ.
 */

// The seat's standing, most-specific first. `former` outranks everything because a removed seat's
// other flags are stale by definition — it may still be linked, and may still have carried an invite.
export type MemberStatus = 'former' | 'joined' | 'invited' | 'placeholder';

export function memberStatus(member: GroupMember): MemberStatus {
  if (!member.isActive) return 'former';
  if (member.isLinked) return 'joined';
  if (member.hasPendingInvite) return 'invited';
  return 'placeholder';
}

// Leaving is a member's own right, so it is never gated on admin — otherwise someone could be held in
// a group. Removing anyone else is admin-only. A former seat has nothing left to remove.
export function canRemoveMember(member: GroupMember, isAdmin: boolean): boolean {
  return member.isActive && (isAdmin || member.isSelf);
}

// A seat someone already holds has nothing to claim, and a former seat is reactivated rather than
// invited — so neither offers an invite even to an admin.
export function canInviteMember(member: GroupMember, isAdmin: boolean): boolean {
  return isAdmin && member.isActive && !member.isLinked;
}

// Only an outstanding invite can be revoked, and only by an admin.
export function canRevokeInvite(member: GroupMember, isAdmin: boolean): boolean {
  return isAdmin && member.isActive && member.hasPendingInvite;
}

// Editing a name or role applies to a live seat; a former one is brought back first.
export function canEditMember(member: GroupMember, isAdmin: boolean): boolean {
  return isAdmin && member.isActive;
}

// The inverse of canEditMember: a former seat is reactivated, not edited.
export function canReactivateMember(member: GroupMember, isAdmin: boolean): boolean {
  return isAdmin && !member.isActive;
}
