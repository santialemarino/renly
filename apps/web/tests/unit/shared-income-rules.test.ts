import { describe, expect, it } from 'vitest';

import {
  canNameOwnDestination,
  hasSharedIncome,
  inactiveSeatNames,
  incomeHolderDisplay,
  isJointlyHeld,
  ownershipDefaultShares,
  rememberedDestination,
  seatNames,
  wasParticipant,
} from '@/app/(protected)/shared/shared-income-rules';
import type { GroupMember } from '@/lib/api/groups';
import type { SharedIncome, SharedIncomeSplit } from '@/lib/api/shared-income';

/*
 * The rules that decide what a shared-income surface shows and offers. Each mirrors a rule the API
 * also enforces, so the failure they guard against is the two disagreeing: a control offered that
 * then 400s, or a saved row that cannot be reopened as what it actually is.
 *
 * Fixtures are deliberately UNEVEN — a 60/40 asset and a collector holding the whole of a three-way
 * split — because an even one cannot tell a wrong answer from a right one: every member's figure is
 * the same, so swapping two of them, or reading `receivedAmount` where `amount` was meant, still
 * looks correct.
 */

function split(overrides: Partial<SharedIncomeSplit> = {}): SharedIncomeSplit {
  return {
    memberId: 1,
    displayName: 'Santi',
    amount: '30000.00',
    receivedAmount: '0',
    isSelf: false,
    ...overrides,
  };
}

function income(overrides: Partial<SharedIncome> = {}): SharedIncome {
  return {
    id: 1,
    groupId: 3,
    date: '2026-09-01',
    amount: '90000.00',
    currency: 'ARS',
    convertedAmount: null,
    category: 'rental_income',
    notes: null,
    splitMethod: 'equal',
    destination: 'distributed',
    sourceInvestmentId: null,
    sourceInvestmentName: null,
    paidToAccountId: null,
    paidToAccountName: null,
    receivedByMemberId: 1,
    receivedByDisplayName: 'Santi',
    myShare: '30000.00',
    splits: [
      split({ memberId: 1, receivedAmount: '90000.00' }),
      split({ memberId: 2, displayName: 'Nico' }),
      split({ memberId: 3, displayName: 'Ana' }),
    ],
    createdAt: '2026-09-01T10:00:00Z',
    updatedAt: '2026-09-01T10:00:00Z',
    ...overrides,
  };
}

function member(overrides: Partial<GroupMember> = {}): GroupMember {
  return {
    id: 1,
    userId: 10,
    displayName: 'Santi',
    role: 'member',
    isActive: true,
    isSelf: false,
    ...overrides,
  } as GroupMember;
}

describe('isJointlyHeld', () => {
  it('reads the stored destination and nothing else', () => {
    expect(isJointlyHeld(income({ destination: 'joint' }))).toBe(true);
    expect(isJointlyHeld(income({ destination: 'distributed' }))).toBe(false);
  });

  /*
   * The case that reading the splits alone gets wrong. A pot with exactly ONE owner has that owner
   * receiving the whole amount, which is indistinguishable from one person collecting it — and a pot
   * with one owner is a supported state, since it is where a buy-out ends.
   */
  it('is joint even when a single owner received the whole amount', () => {
    const singleOwner = income({
      destination: 'joint',
      receivedByMemberId: null,
      receivedByDisplayName: null,
      splits: [split({ memberId: 1, amount: '90000.00', receivedAmount: '90000.00' })],
    });
    expect(isJointlyHeld(singleOwner)).toBe(true);
  });

  it('is NOT joint when one person collected it, whatever the splits look like', () => {
    // The mirror of the case above: the same split SHAPE with the other destination.
    const collected = income({
      destination: 'distributed',
      splits: [split({ memberId: 1, amount: '90000.00', receivedAmount: '90000.00' })],
    });
    expect(isJointlyHeld(collected)).toBe(false);
  });
});

describe('incomeHolderDisplay', () => {
  it('names the person who collected it', () => {
    expect(incomeHolderDisplay(income())).toEqual({ kind: 'member', displayName: 'Santi' });
  });

  it('names the shared account when the money stayed joint', () => {
    const joint = income({
      destination: 'joint',
      receivedByMemberId: null,
      receivedByDisplayName: null,
      paidToAccountId: 7,
      paidToAccountName: 'Casa ARS',
    });
    expect(incomeHolderDisplay(joint)).toEqual({ kind: 'joint', accountName: 'Casa ARS' });
  });

  /*
   * The account's name can be absent even on a joint row: a viewer excluded from that pot sees the id
   * without the name. There is nothing honest to add, so the caller says only that it stayed joint.
   */
  it('reports joint with no name rather than inventing one', () => {
    const hidden = income({
      destination: 'joint',
      receivedByMemberId: null,
      receivedByDisplayName: null,
      paidToAccountId: 7,
      paidToAccountName: null,
    });
    expect(incomeHolderDisplay(hidden)).toEqual({ kind: 'joint', accountName: null });
  });
});

describe('canNameOwnDestination', () => {
  it('is true only for the viewer’s own seat', () => {
    expect(canNameOwnDestination(4, 4)).toBe(true);
    expect(canNameOwnDestination(4, 9)).toBe(false);
  });

  /*
   * A viewer with no seat in the group cannot name an account either. Both halves matter: the API
   * requires a named account to belong to the recipient, and the policies hide everyone else's — so
   * offering the picker for another member could only produce a 404.
   */
  it('is false for a viewer holding no seat, and for a row nobody received', () => {
    expect(canNameOwnDestination(4, null)).toBe(false);
    expect(canNameOwnDestination(null, 4)).toBe(false);
    /*
     * BOTH null is the pair the seat guard exists for, and the only one a bare equality gets wrong:
     * `null === null` is true. It is reachable — a viewer with no seat, on a form whose recipient
     * field is still blank — and offering them the account picker would put a field on screen for a
     * recipient nobody has named. A sweep found this case untested.
     */
    expect(canNameOwnDestination(null, null)).toBe(false);
  });
});

describe('ownershipDefaultShares', () => {
  // F1. The 60/40 is what makes this able to fail: an even split would produce the same map whichever
  // percentage was read for which member.
  it('keys each owner’s percentage by their seat', () => {
    const { shares, missingOwners } = ownershipDefaultShares(
      [
        { memberId: 1, percentage: '60.00' },
        { memberId: 2, percentage: '40.00' },
      ],
      [1, 2, 3],
    );
    expect(shares.get(1)).toBe('60.00');
    expect(shares.get(2)).toBe('40.00');
    expect(shares.size).toBe(2);
    expect(missingOwners).toEqual([]);
  });

  /*
   * A zero-percent holder is dropped rather than included at 0: they own none of the asset, so
   * including them would put a participant with nothing in the split and make the percentages the
   * form pre-fills read as a list of people who share the income when one of them does not.
   */
  it('drops a holder of nothing', () => {
    const { shares } = ownershipDefaultShares(
      [
        { memberId: 1, percentage: '100.00' },
        { memberId: 2, percentage: '0.00' },
      ],
      [1, 2],
    );
    expect([...shares.keys()]).toEqual([1]);
  });

  it('a holder of nothing who has left the group does not block the pre-fill', () => {
    // They own none of it, so their absence changes no percentage — the shares still reach 100.
    const { shares, missingOwners } = ownershipDefaultShares(
      [
        { memberId: 1, percentage: '100.00' },
        { memberId: 9, percentage: '0.00' },
      ],
      [1],
    );
    expect(shares.get(1)).toBe('100.00');
    expect(missingOwners).toEqual([]);
  });

  /*
   * THE case this shape exists for. A member who leaves the group keeps any pot units they hold, so a
   * co-owned asset can genuinely be owned partly by somebody with no row in the split editor. Handing
   * back the remaining 60 would give the user percentages the API refuses for a division they never
   * chose — so nothing comes back, and the caller says whose absence stopped it.
   */
  it('refuses to pre-fill when an owner has no seat to put their share on', () => {
    const { shares, missingOwners } = ownershipDefaultShares(
      [
        { memberId: 1, percentage: '60.00' },
        { memberId: 9, percentage: '40.00' },
      ],
      [1, 2],
    );
    expect(shares.size).toBe(0);
    expect(missingOwners).toEqual([9]);
  });

  it('never rescales the owners who are left', () => {
    // The one thing this must not do: 60 becoming 100 is a division nobody agreed to.
    const { shares } = ownershipDefaultShares(
      [
        { memberId: 1, percentage: '60.00' },
        { memberId: 9, percentage: '40.00' },
      ],
      [1],
    );
    expect(shares.get(1)).toBeUndefined();
  });

  it('is empty when the asset’s pot has no ownership on record', () => {
    const { shares, missingOwners } = ownershipDefaultShares([], [1, 2]);
    expect(shares.size).toBe(0);
    // Distinct from the case above, and the caller says something different: nothing is divided yet,
    // rather than somebody's share being unplaceable.
    expect(missingOwners).toEqual([]);
  });
});

describe('seatNames', () => {
  it('names the seats the roster holds, former members included', () => {
    // The roster carries inactive seats, which is exactly why it can answer whose share was unplaceable.
    expect(
      seatNames(
        [1, 2],
        [
          member({ id: 1, displayName: 'Santi' }),
          member({ id: 2, displayName: 'Ana', isActive: false }),
        ],
      ),
    ).toEqual(['Santi', 'Ana']);
  });

  it('says nothing for an id the roster does not hold', () => {
    expect(seatNames([404], [member({ id: 1 })])).toEqual([]);
  });
});

describe('rememberedDestination', () => {
  // The list arrives NEWEST FIRST from the API, so the first match is the most recent. A fixture with
  // two entries for one source in opposite destinations is what proves the order is relied on.
  const history = [
    income({ id: 9, sourceInvestmentId: 4, destination: 'joint' }),
    income({ id: 8, sourceInvestmentId: 4, destination: 'distributed' }),
    income({ id: 7, sourceInvestmentId: 5, destination: 'distributed' }),
  ];

  it('remembers the most recent destination for that source', () => {
    expect(rememberedDestination(history, 4)).toBe('joint');
    expect(rememberedDestination(history, 5)).toBe('distributed');
  });

  it('remembers the no-source case too', () => {
    // Somebody who records untied income the same way every month gets the same benefit as somebody
    // with a property, which is why the match includes null rather than skipping it.
    const untied = [income({ id: 6, sourceInvestmentId: null, destination: 'joint' })];
    expect(rememberedDestination(untied, null)).toBe('joint');
  });

  it('returns null for a source never recorded, so the caller picks the opening default', () => {
    expect(rememberedDestination(history, 99)).toBeNull();
    expect(rememberedDestination([], 4)).toBeNull();
  });

  it('does not match a source against the no-source case', () => {
    // The failure this catches: treating null as a wildcard, so the first row of any source would be
    // remembered for untied income and vice versa.
    const onlySourced = [income({ id: 5, sourceInvestmentId: 4, destination: 'joint' })];
    expect(rememberedDestination(onlySourced, null)).toBeNull();
  });
});

describe('wasParticipant', () => {
  it('counts anyone entitled to a share', () => {
    expect(wasParticipant(split({ amount: '30000.00', receivedAmount: '0' }))).toBe(true);
    expect(wasParticipant(split({ amount: '30000.00', receivedAmount: '90000.00' }))).toBe(true);
  });

  /*
   * The one shape that is not a participant: entitled to nothing while holding something — a custodian
   * who collected the rent and takes no share of it, the mirror of a payer who took no part in a bill.
   */
  it('excludes a collector entitled to nothing', () => {
    expect(wasParticipant(split({ amount: '0', receivedAmount: '90000.00' }))).toBe(false);
  });

  // A row of two zeros IS a participant: an `exact` split may deliberately give somebody nothing, and
  // that is a person who was included rather than one who was not.
  it('counts a row of two zeros', () => {
    expect(wasParticipant(split({ amount: '0', receivedAmount: '0' }))).toBe(true);
  });
});

describe('inactiveSeatNames', () => {
  const members = [
    member({ id: 1, displayName: 'Santi' }),
    member({ id: 2, displayName: 'Nico', isActive: false }),
    member({ id: 3, displayName: 'Ana', isActive: false }),
  ];

  it('names only the seats that have left', () => {
    expect(inactiveSeatNames([1, 2, 3], members)).toEqual(['Nico', 'Ana']);
  });

  it('says nothing when every named seat is active', () => {
    expect(inactiveSeatNames([1], members)).toEqual([]);
  });

  // A seat from another group is not in the roster at all. It is refused by the API for a different
  // reason, so naming it here as "former" would be the wrong explanation.
  it('ignores an id the roster does not hold', () => {
    expect(inactiveSeatNames([404], members)).toEqual([]);
  });
});

describe('hasSharedIncome', () => {
  it('distinguishes a group with nothing recorded from one that has earned', () => {
    expect(hasSharedIncome([])).toBe(false);
    expect(hasSharedIncome([income()])).toBe(true);
  });
});
