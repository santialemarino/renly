import { describe, expect, it } from 'vitest';

import {
  canNameOwnInstrument,
  expensePayerDisplay,
  inactiveSeatNames,
  isJointlyFunded,
  wasParticipant,
} from '@/app/(protected)/shared/shared-expense-rules';
import type { GroupMember } from '@/lib/api/groups';
import type { SharedExpense, SharedExpenseSplit } from '@/lib/api/shared-expenses';

/*
 * The rules that decide what a shared expense's surface shows and offers. Each mirrors a rule the API
 * also enforces, so the failure they guard against is the two disagreeing: a control offered that
 * then 400s, or a saved expense that cannot be reopened as what it actually is.
 *
 * Fixtures are deliberately UNEVEN — a three-way 3:2:1 split of 90,000 rather than an equal one —
 * because an equal split cannot tell a wrong answer from a right one: every member's figure is the
 * same, so swapping two of them, or reading `paidAmount` where `amount` was meant, still looks
 * correct.
 */

function seat(overrides: Partial<GroupMember> = {}): GroupMember {
  return {
    id: 1,
    displayName: 'Santi',
    role: 'admin',
    isActive: true,
    isLinked: true,
    isSelf: true,
    hasPendingInvite: false,
    joinedAt: '2026-08-01T00:00:00Z',
    createdAt: '2026-08-01T00:00:00Z',
    updatedAt: '2026-08-01T00:00:00Z',
    ...overrides,
  };
}

function split(overrides: Partial<SharedExpenseSplit> = {}): SharedExpenseSplit {
  return {
    memberId: 1,
    displayName: 'Santi',
    amount: '45000.00',
    paidAmount: '0.00',
    isSelf: true,
    ...overrides,
  };
}

function expense(overrides: Partial<SharedExpense> = {}): SharedExpense {
  return {
    id: 1,
    groupId: 7,
    date: '2026-08-30',
    amount: '90000.00',
    currency: 'ARS',
    convertedAmount: null,
    category: 'food',
    notes: null,
    splitMethod: 'shares',
    paidFromAccountId: null,
    paidFromAccountName: null,
    paymentMethod: null,
    creditCardId: null,
    payerMemberId: 1,
    payerDisplayName: 'Santi',
    myShare: '45000.00',
    splits: [
      split({ memberId: 1, displayName: 'Santi', amount: '45000.00', paidAmount: '90000.00' }),
      split({ memberId: 2, displayName: 'Nico', amount: '30000.00', isSelf: false }),
      split({ memberId: 3, displayName: 'Ana', amount: '15000.00', isSelf: false }),
    ],
    createdAt: '2026-08-30T10:00:00Z',
    updatedAt: '2026-08-30T10:00:00Z',
    ...overrides,
  };
}

describe('isJointlyFunded', () => {
  it('reads the API’s own null payer rather than guessing from the splits', () => {
    expect(isJointlyFunded(expense())).toBe(false);
    expect(isJointlyFunded(expense({ payerMemberId: null, payerDisplayName: null }))).toBe(true);
  });

  /*
   * The defect 5a fixed, in reverse: a pot with ONE owner produces splits identical in shape to one
   * member paying out of their own pocket — a single member fronting the whole amount. Only the
   * funding tells them apart, and the API answers that question in `payerMemberId`.
   */
  it('calls a single-owner pot joint, even though one member fronted the whole amount', () => {
    const singleOwnerPot = expense({
      payerMemberId: null,
      payerDisplayName: null,
      paidFromAccountId: 12,
      paidFromAccountName: 'Joint account',
      splits: [
        split({ memberId: 1, amount: '45000.00', paidAmount: '90000.00' }),
        split({ memberId: 2, displayName: 'Nico', amount: '45000.00', isSelf: false }),
      ],
    });
    expect(isJointlyFunded(singleOwnerPot)).toBe(true);
    expect(expensePayerDisplay(singleOwnerPot)).toEqual({
      kind: 'joint',
      accountName: 'Joint account',
    });
  });
});

describe('expensePayerDisplay', () => {
  it('names the member who fronted a private payment', () => {
    expect(expensePayerDisplay(expense())).toEqual({ kind: 'member', displayName: 'Santi' });
  });

  // The account belongs to a pot the caller can see, so the name comes back with the row.
  it('names the shared account when there is one to name', () => {
    expect(
      expensePayerDisplay(
        expense({ payerMemberId: null, payerDisplayName: null, paidFromAccountName: 'Casa' }),
      ),
    ).toEqual({ kind: 'joint', accountName: 'Casa' });
  });

  // A private account belonging to another member is hidden by the policies, so the id arrives
  // without a name and there is nothing honest to add.
  it('states joint money with no name when the account is hidden from the caller', () => {
    expect(
      expensePayerDisplay(
        expense({ payerMemberId: null, payerDisplayName: null, paidFromAccountName: null }),
      ),
    ).toEqual({ kind: 'joint', accountName: null });
  });
});

describe('canNameOwnInstrument', () => {
  it('is true only for the viewer’s own seat', () => {
    expect(canNameOwnInstrument(4, 4)).toBe(true);
    expect(canNameOwnInstrument(5, 4)).toBe(false);
  });

  // Joint money has no payer at all, and a viewer with no seat has no instrument to offer.
  it('is false with no payer and false with no seat', () => {
    expect(canNameOwnInstrument(null, 4)).toBe(false);
    expect(canNameOwnInstrument(4, null)).toBe(false);
    expect(canNameOwnInstrument(null, null)).toBe(false);
  });
});

describe('inactiveSeatNames', () => {
  const roster = [
    seat({ id: 1, displayName: 'Santi' }),
    seat({ id: 2, displayName: 'Nico', isSelf: false }),
    seat({ id: 3, displayName: 'Ana', isSelf: false, isActive: false }),
  ];

  it('names only the seats that have left', () => {
    expect(inactiveSeatNames([1, 2, 3], roster)).toEqual(['Ana']);
    expect(inactiveSeatNames([1, 2], roster)).toEqual([]);
  });

  // An id the roster does not hold is not a former member — it is nothing this group can name, and
  // reporting it as departed would put a blank in the sentence.
  it('ignores an id that is not on the roster at all', () => {
    expect(inactiveSeatNames([99], roster)).toEqual([]);
  });

  it('keeps the order the ids were named in, so the sentence reads as the form does', () => {
    const twoFormer = [
      ...roster,
      seat({ id: 4, displayName: 'Bea', isSelf: false, isActive: false }),
    ];
    expect(inactiveSeatNames([4, 3], twoFormer)).toEqual(['Bea', 'Ana']);
  });
});

describe('wasParticipant', () => {
  it('counts anyone who consumed something', () => {
    expect(wasParticipant(split({ amount: '30000.00', paidAmount: '0.00' }))).toBe(true);
    expect(wasParticipant(split({ amount: '30000.00', paidAmount: '90000.00' }))).toBe(true);
  });

  // The one shape that is not a participant: fronted money, consumed none. A payer who was not in on
  // the bill (D33), or a pot owner whose joint account paid for a meal they missed.
  it('excludes a payer who took no part', () => {
    expect(wasParticipant(split({ amount: '0.00', paidAmount: '90000.00' }))).toBe(false);
  });

  // An exact split may deliberately give somebody nothing. They were there.
  it('counts a participant explicitly given zero', () => {
    expect(wasParticipant(split({ amount: '0.00', paidAmount: '0.00' }))).toBe(true);
  });
});
