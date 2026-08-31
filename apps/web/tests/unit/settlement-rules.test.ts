import { describe, expect, it } from 'vitest';

import {
  balanceMagnitude,
  balancesEmptyState,
  balanceStanding,
  canAttachOwnLeg,
  canUnconfirmSettlement,
  canWriteOffSuggestion,
  hasOpenBalances,
  legCrossesCurrency,
  ownLegAccountId,
  ownLegAccounts,
  ownLegAmount,
  ownSettlementSide,
  suggestionSide,
  suggestionVoice,
} from '@/app/(protected)/shared/settlement-rules';
import type { Account } from '@/lib/api/accounts';
import type {
  GroupCurrencyBalance,
  GroupSettlement,
  GroupSettleSuggestion,
} from '@/lib/api/group-settlements';

/*
 * The rules behind the balances and settle-up surface.
 *
 * Two of them mirror API rules the response carries no field for — who may take a confirmation back,
 * and whose cash leg a caller may attach — so the failure they guard against is a control that 403s.
 * The rest decide which sentence a figure is stated in, where getting it backwards produces a
 * plausible line that says the opposite of the truth.
 *
 * Every fixture is ASYMMETRIC: the payer, the payee and the viewer are three different seats wherever
 * they can be, because a settlement whose two sides are interchangeable cannot tell a rule that reads
 * `from` from one that reads `to`.
 */

const ME = 10;
const PAYER = 11;
const PAYEE = 12;

function settlement(overrides: Partial<GroupSettlement> = {}): GroupSettlement {
  return {
    id: 1,
    groupId: 7,
    fromMemberId: PAYER,
    fromDisplayName: 'Nico',
    toMemberId: PAYEE,
    toDisplayName: 'Ana',
    date: '2026-08-30',
    amount: '30000.00',
    currency: 'ARS',
    status: 'pending',
    fromAccountId: null,
    fromAmount: null,
    toAccountId: null,
    toAmount: null,
    confirmedAt: null,
    notes: null,
    canConfirm: false,
    canDelete: false,
    createdAt: '2026-08-30T10:00:00Z',
    updatedAt: '2026-08-30T10:00:00Z',
    ...overrides,
  };
}

function suggestion(overrides: Partial<GroupSettleSuggestion> = {}): GroupSettleSuggestion {
  return {
    fromMemberId: PAYER,
    fromDisplayName: 'Nico',
    toMemberId: PAYEE,
    toDisplayName: 'Ana',
    amount: '30000.00',
    ...overrides,
  };
}

function account(overrides: Partial<Account> = {}): Account {
  return {
    id: 100,
    name: 'Brubank',
    type: 'bank',
    currency: 'ARS',
    openingBalance: '0.00',
    openingDate: '2026-01-01',
    balance: '0.00',
    isActive: true,
    notes: null,
    hasLinks: false,
    lastReconciledDate: null,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('ownSettlementSide', () => {
  it('reads the payer’s side and the payee’s side apart', () => {
    expect(ownSettlementSide(settlement(), PAYER)).toBe('outgoing');
    expect(ownSettlementSide(settlement(), PAYEE)).toBe('incoming');
  });

  // A third member may record and see the settlement without being in it — they have no leg at all.
  it('is null for a member on neither side, and for no seat', () => {
    expect(ownSettlementSide(settlement(), ME)).toBeNull();
    expect(ownSettlementSide(settlement(), null)).toBeNull();
  });
});

describe('canAttachOwnLeg', () => {
  it('lets either party attach theirs while pending', () => {
    expect(canAttachOwnLeg(settlement(), PAYER)).toBe(true);
    expect(canAttachOwnLeg(settlement(), PAYEE)).toBe(true);
  });

  /*
   * Deliberately still allowed once confirmed. What confirmation vouches for is the amount and the
   * fact of the payment; which of the caller's own accounts it passed through changes neither, and
   * moves nobody else's balance.
   */
  it('stays available on a confirmed settlement', () => {
    expect(canAttachOwnLeg(settlement({ status: 'confirmed' }), PAYEE)).toBe(true);
  });

  // A write-off moved no money, so there is no leg to attach (409 group_settlement_write_off_has_no_leg).
  it('is refused on a write-off, for both parties', () => {
    expect(canAttachOwnLeg(settlement({ status: 'written_off' }), PAYER)).toBe(false);
    expect(canAttachOwnLeg(settlement({ status: 'written_off' }), PAYEE)).toBe(false);
  });

  it('is refused for a member on neither side', () => {
    expect(canAttachOwnLeg(settlement(), ME)).toBe(false);
  });
});

describe('canUnconfirmSettlement', () => {
  // The payee's alone, for the same reason only they may confirm: it is their word being withdrawn.
  it('is the payee’s alone, and only once confirmed', () => {
    expect(canUnconfirmSettlement(settlement({ status: 'confirmed' }), PAYEE)).toBe(true);
    expect(canUnconfirmSettlement(settlement({ status: 'confirmed' }), PAYER)).toBe(false);
    expect(canUnconfirmSettlement(settlement({ status: 'confirmed' }), ME)).toBe(false);
  });

  it('is not offered while pending or on a write-off', () => {
    expect(canUnconfirmSettlement(settlement({ status: 'pending' }), PAYEE)).toBe(false);
    expect(canUnconfirmSettlement(settlement({ status: 'written_off' }), PAYEE)).toBe(false);
  });
});

describe('ownLegAccountId / ownLegAmount', () => {
  const crossCurrency = settlement({
    fromAccountId: 100,
    fromAmount: '40.00',
    toAccountId: 200,
    toAmount: '52000.00',
  });

  // The two legs carry different accounts and different figures on purpose: reading the wrong side
  // would show the other person's account and their amount.
  it('reads each side’s own account and figure', () => {
    expect(ownLegAccountId(crossCurrency, PAYER)).toBe(100);
    expect(ownLegAmount(crossCurrency, PAYER)).toBe('40.00');
    expect(ownLegAccountId(crossCurrency, PAYEE)).toBe(200);
    expect(ownLegAmount(crossCurrency, PAYEE)).toBe('52000.00');
  });

  it('is null for a member on neither side', () => {
    expect(ownLegAccountId(crossCurrency, ME)).toBeNull();
    expect(ownLegAmount(crossCurrency, ME)).toBeNull();
  });

  // A same-currency leg stores no amount: the account moved exactly what came off the bucket, and a
  // second copy of the figure would be a second thing to keep in step.
  it('reports no figure for a same-currency leg that has an account', () => {
    const sameCurrency = settlement({ fromAccountId: 100, fromAmount: null });
    expect(ownLegAccountId(sameCurrency, PAYER)).toBe(100);
    expect(ownLegAmount(sameCurrency, PAYER)).toBeNull();
  });
});

describe('canWriteOffSuggestion', () => {
  // Giving up a claim belongs to whoever holds it — the payee (403 group_settlement_not_creditor).
  it('is the creditor’s alone', () => {
    expect(canWriteOffSuggestion(suggestion(), PAYEE)).toBe(true);
    expect(canWriteOffSuggestion(suggestion(), PAYER)).toBe(false);
    expect(canWriteOffSuggestion(suggestion(), ME)).toBe(false);
    expect(canWriteOffSuggestion(suggestion(), null)).toBe(false);
  });
});

describe('suggestionVoice', () => {
  /*
   * Order-dependent with no other guard: swapping the first two branches produces "Nico pays you"
   * where you in fact owe Nico — a sentence a reader would believe, and one no type check can see.
   */
  it('states the caller paying, the caller being paid, and two other people', () => {
    expect(suggestionVoice(suggestion(), PAYER)).toBe('youPay');
    expect(suggestionVoice(suggestion(), PAYEE)).toBe('paysYou');
    expect(suggestionVoice(suggestion(), ME)).toBe('pays');
    expect(suggestionVoice(suggestion(), null)).toBe('pays');
  });
});

describe('suggestionSide', () => {
  // Defined from the voice, so the sentence the dialog says and the column it writes cannot diverge.
  it('agrees with the voice on every case', () => {
    expect(suggestionSide(suggestion(), PAYER)).toBe('outgoing');
    expect(suggestionSide(suggestion(), PAYEE)).toBe('incoming');
    expect(suggestionSide(suggestion(), ME)).toBeNull();
    expect(suggestionSide(suggestion(), null)).toBeNull();
  });
});

describe('balanceStanding', () => {
  it('separates being owed, owing, and being square', () => {
    expect(balanceStanding('30000.00')).toBe('owed');
    expect(balanceStanding('-30000.00')).toBe('owing');
    expect(balanceStanding('0.00')).toBe('square');
  });

  // A cent either way is still a position: square is exactly zero, never "close to zero".
  it('treats a single cent as a real position', () => {
    expect(balanceStanding('0.01')).toBe('owed');
    expect(balanceStanding('-0.01')).toBe('owing');
  });
});

describe('balanceMagnitude', () => {
  // The cell carries its own sign, so a minus inside it would show twice.
  it('drops the sign without touching the digits', () => {
    expect(balanceMagnitude('-30000.55')).toBe('30000.55');
    expect(balanceMagnitude('30000.55')).toBe('30000.55');
    expect(balanceMagnitude('0.00')).toBe('0.00');
  });
});

describe('legCrossesCurrency', () => {
  it('is true only when the leg is denominated differently from the bucket', () => {
    expect(legCrossesCurrency('USD', 'ARS')).toBe(true);
    expect(legCrossesCurrency('ARS', 'ARS')).toBe(false);
  });

  /*
   * No leg currency is no account named, so there is nothing to cross. The forms clear the two
   * together, and this is what stops a stale currency keeping the amount field alive — and required —
   * for a leg the user has just removed.
   */
  it('is false with no leg currency at all', () => {
    expect(legCrossesCurrency(undefined, 'ARS')).toBe(false);
    expect(legCrossesCurrency('', 'ARS')).toBe(false);
  });
});

describe('ownLegAccounts', () => {
  /*
   * Active-only mirrors every other money form; ANY currency is offered, because a settlement
   * crossing currencies is the one moment somebody actually agreed a rate — filtering it out would
   * remove the case the two leg amounts exist for.
   */
  it('offers active accounts in every currency', () => {
    const accounts = [
      account({ id: 1, currency: 'ARS' }),
      account({ id: 2, currency: 'USD' }),
      account({ id: 3, currency: 'ARS', isActive: false }),
    ];
    expect(ownLegAccounts(accounts).map((a) => a.id)).toEqual([1, 2]);
  });
});

describe('balancesEmptyState / hasOpenBalances', () => {
  /*
   * A settled bucket disappears from the response entirely, so an empty list means one of two
   * opposite things — and each deserves the other's sentence never being shown in its place.
   */
  it('tells a group with nothing recorded from one that is all square', () => {
    expect(balancesEmptyState(false)).toBe('nothingShared');
    expect(balancesEmptyState(true)).toBe('allSquare');
  });

  it('reports whether any bucket is open at all', () => {
    expect(hasOpenBalances([])).toBe(false);
    expect(hasOpenBalances([{ currency: 'ARS' } as GroupCurrencyBalance])).toBe(true);
  });
});
