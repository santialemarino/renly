import { describe, expect, it } from 'vitest';

import {
  canEditMember,
  canInviteMember,
  canReactivateMember,
  canRemoveMember,
  canRevokeInvite,
  memberStatus,
} from '@/app/(protected)/shared/[groupId]/member-permissions';
import type { GroupMember } from '@/lib/api/groups';

/*
 * These rules are order-dependent and decide what a roster row says and offers. Nothing else guards
 * them: swap two branches of `memberStatus` and a removed member reads as "invited", which type
 * checking cannot see and a screenshot would not obviously contradict.
 *
 * The cases below are deliberately built from every meaningful COMBINATION rather than one example
 * per rule, because the bugs here are the combinations — a former seat that is still linked, a
 * placeholder carrying an invite, the viewer's own seat.
 */
function member(over: Partial<GroupMember> = {}): GroupMember {
  return {
    id: 1,
    displayName: 'Ana',
    role: 'member',
    isActive: true,
    isLinked: false,
    isSelf: false,
    hasPendingInvite: false,
    joinedAt: null,
    createdAt: '2026-08-22T00:00:00Z',
    updatedAt: '2026-08-22T00:00:00Z',
    ...over,
  };
}

describe('memberStatus', () => {
  it.each([
    ['a seat nobody has claimed', {}, 'placeholder'],
    ['a seat with an outstanding invite', { hasPendingInvite: true }, 'invited'],
    ['a seat an account holds', { isLinked: true }, 'joined'],
    ['a removed seat', { isActive: false }, 'former'],
  ])('reports %s as %s', (_label, over, expected) => {
    expect(memberStatus(member(over))).toBe(expected);
  });

  it('reports a removed seat as former even when it is still linked', () => {
    // `former` has to outrank `joined`: a removed member keeps their account link, so checking
    // isLinked first would show them as an ordinary member of the group they were removed from.
    expect(memberStatus(member({ isActive: false, isLinked: true }))).toBe('former');
  });

  it('reports a removed seat as former even when an invite is still recorded against it', () => {
    expect(memberStatus(member({ isActive: false, hasPendingInvite: true }))).toBe('former');
  });

  it('prefers joined over invited when a seat is somehow both', () => {
    // Claiming consumes the invite, so this pair should not occur — but if it ever did, "joined" is
    // the truth and "invited" would tell the group someone has not arrived when they have.
    expect(memberStatus(member({ isLinked: true, hasPendingInvite: true }))).toBe('joined');
  });
});

describe('canRemoveMember', () => {
  it('lets an admin remove anyone active', () => {
    expect(canRemoveMember(member(), true)).toBe(true);
  });

  it('lets a plain member remove their OWN seat — leaving must never need an admin', () => {
    expect(canRemoveMember(member({ isSelf: true }), false)).toBe(true);
  });

  it('does not let a plain member remove someone else', () => {
    expect(canRemoveMember(member(), false)).toBe(false);
  });

  it('offers nothing on a seat that is already removed', () => {
    for (const isAdmin of [true, false]) {
      expect(canRemoveMember(member({ isActive: false }), isAdmin)).toBe(false);
      expect(canRemoveMember(member({ isActive: false, isSelf: true }), isAdmin)).toBe(false);
    }
  });
});

describe('canInviteMember', () => {
  it('offers an invite only on an active, unclaimed seat, and only to an admin', () => {
    expect(canInviteMember(member(), true)).toBe(true);
    expect(canInviteMember(member(), false)).toBe(false);
    // Already claimed — the API refuses this with group_seat_taken.
    expect(canInviteMember(member({ isLinked: true }), true)).toBe(false);
    // Removed — the supported move is to bring them back, not to invite them again.
    expect(canInviteMember(member({ isActive: false }), true)).toBe(false);
  });
});

describe('canRevokeInvite', () => {
  it('offers a revoke only where an invite is actually outstanding', () => {
    expect(canRevokeInvite(member({ hasPendingInvite: true }), true)).toBe(true);
    expect(canRevokeInvite(member(), true)).toBe(false);
    expect(canRevokeInvite(member({ hasPendingInvite: true }), false)).toBe(false);
    expect(canRevokeInvite(member({ isActive: false, hasPendingInvite: true }), true)).toBe(false);
  });
});

describe('canEditMember and canReactivateMember', () => {
  it('are mutually exclusive for an admin — a seat is edited or brought back, never both', () => {
    for (const over of [
      {},
      { isLinked: true },
      { isActive: false },
      { isActive: false, isLinked: true },
    ]) {
      const m = member(over);
      expect(canEditMember(m, true) && canReactivateMember(m, true)).toBe(false);
      expect(canEditMember(m, true) || canReactivateMember(m, true)).toBe(true);
    }
  });

  it('offer nothing at all to a plain member', () => {
    for (const over of [{}, { isActive: false }, { isSelf: true }]) {
      expect(canEditMember(member(over), false)).toBe(false);
      expect(canReactivateMember(member(over), false)).toBe(false);
    }
  });
});

describe('what a plain member is offered on their own row', () => {
  it('is leaving, and nothing else', () => {
    // The one case a member has any control at all. Pinning the whole set here is what would catch a
    // predicate quietly widening to grant a member an admin action on themselves.
    const own = member({ isSelf: true, isLinked: true });
    expect({
      remove: canRemoveMember(own, false),
      invite: canInviteMember(own, false),
      revoke: canRevokeInvite(own, false),
      edit: canEditMember(own, false),
      reactivate: canReactivateMember(own, false),
    }).toEqual({ remove: true, invite: false, revoke: false, edit: false, reactivate: false });
  });
});
