import { describe, expect, it } from 'vitest';

import {
  balanceMagnitude,
  balancesEmptyState,
  balanceStanding,
  bucketOutOfReach,
  bucketPartlyCleared,
  canAttachOwnLeg,
  canUnconfirmSettlement,
  canWriteOffSuggestion,
  hasAnySharedFlow,
  hasOpenBalances,
  legCrossesCurrency,
  ownLegAccountId,
  ownLegAccounts,
  ownLegAmount,
  ownSettlementSide,
  plannedRows,
  planNeedsConfirming,
  selectedSpilloverCurrencies,
  suggestionSide,
  suggestionVoice,
} from '@/app/(protected)/shared/settlement-rules';
import type { Account } from '@/lib/api/accounts';
import type {
  GroupCurrencyBalance,
  GroupSettlement,
  GroupSettlementPlan,
  GroupSettlementPlanBucket,
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

describe('hasAnySharedFlow', () => {
  // What feeds the sentence below. INCOME ALONE has to count: a group whose only shared record is a
  // piece of income everyone has been paid their share of is square, not empty, and telling them to
  // add their first expense would be wrong about a ledger they can see right above.
  it('counts either flow, and says nothing shared only when both are empty', () => {
    expect(hasAnySharedFlow([], [])).toBe(false);
    expect(hasAnySharedFlow([{}], [])).toBe(true);
    expect(hasAnySharedFlow([], [{}])).toBe(true);
    expect(hasAnySharedFlow([{}], [{}])).toBe(true);
  });

  it('feeds the empty-state sentence, so income alone reads as all square', () => {
    expect(balancesEmptyState(hasAnySharedFlow([], [{}]))).toBe('allSquare');
    expect(balancesEmptyState(hasAnySharedFlow([], []))).toBe('nothingShared');
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

/*
 * The overpay waterfall's surface rules.
 *
 * Every figure a plan carries is the SERVER's, and these decide only what to render — which is the
 * line that matters: the moment one of these recomputed an amount it would be a second implementation
 * of the allocation, and the payer would confirm one number while another was recorded.
 */

function planBucket(overrides: Partial<GroupSettlementPlanBucket> = {}): GroupSettlementPlanBucket {
  return {
    currency: 'USD',
    outstanding: '10.00',
    cost: '10375.00',
    amount: '10.00',
    appliedCost: '10375.00',
    selected: true,
    ...overrides,
  };
}

function plan(overrides: Partial<GroupSettlementPlan> = {}): GroupSettlementPlan {
  return {
    currency: 'ARS',
    amount: '45000.00',
    primaryOutstanding: '30000.00',
    excess: '15000.00',
    primaryAmount: '34625.00',
    buckets: [planBucket()],
    leftover: '4625.00',
    skippedCurrencies: [],
    ...overrides,
  };
}

describe('planNeedsConfirming', () => {
  it('is true when an excess has somewhere to go', () => {
    expect(planNeedsConfirming(plan())).toBe(true);
  });

  it('is false when the payment does not exceed its bucket', () => {
    // The preview returns no buckets at all in that case, which is the same signal as below.
    expect(planNeedsConfirming(plan({ excess: '0', buckets: [] }))).toBe(false);
  });

  /*
   * The case that decides whether the confirm step exists at all.
   *
   * An excess with nowhere to go is not a plan — the payment simply overshoots its own bucket and
   * flips it, which is D30 and needs no confirming because the payer typed the number. Treating this
   * as needing confirmation would put an empty step in front of every ordinary overpayment.
   */
  it('is false when there is an excess but no other balance to reach', () => {
    expect(planNeedsConfirming(plan({ excess: '15000.00', buckets: [] }))).toBe(false);
  });
});

describe('plannedRows', () => {
  it('names the paid bucket first, then each one the excess reached', () => {
    expect(plannedRows(plan())).toEqual([
      { currency: 'ARS', amount: '34625.00' },
      { currency: 'USD', amount: '10.00' },
    ]);
  });

  /*
   * `primaryAmount` is READ, never derived from `primaryOutstanding + leftover` here.
   *
   * The two agree in every ordinary case, which is exactly why deriving it would look correct: it is
   * the partial payment — where the paid bucket takes what the payment covers rather than its whole
   * balance — that separates them. The fixture below states a primaryAmount the arithmetic would not
   * produce, and the rule must report the server's answer.
   */
  it('reports the server’s figure for the paid bucket rather than recomputing it', () => {
    const rows = plannedRows(plan({ primaryAmount: '12000.00', leftover: '0' }));
    expect(rows[0]).toEqual({ currency: 'ARS', amount: '12000.00' });
  });

  it('writes no row for the paid bucket when the payment covered none of it', () => {
    // Paying pesos purely to clear a dollar debt: there is no peso balance to write against.
    expect(plannedRows(plan({ primaryAmount: '0', primaryOutstanding: '0' }))).toEqual([
      { currency: 'USD', amount: '10.00' },
    ]);
  });

  it('leaves out a bucket the excess never reached', () => {
    const rows = plannedRows(
      plan({
        buckets: [planBucket({ amount: '0', appliedCost: '0' }), planBucket({ currency: 'BRL' })],
      }),
    );
    expect(rows.map((row) => row.currency)).toEqual(['ARS', 'BRL']);
  });
});

describe('selectedSpilloverCurrencies', () => {
  it('names only the buckets still ticked', () => {
    const result = selectedSpilloverCurrencies(
      plan({ buckets: [planBucket(), planBucket({ currency: 'BRL', selected: false })] }),
    );
    expect(result).toEqual(['USD']);
  });

  /*
   * An empty list is a real answer and NOT the same as omitting the field.
   *
   * Absent means "every bucket the excess can reach", so an unticked-everything plan that sent nothing
   * would spill into all of them — the exact opposite of what the payer asked for.
   */
  it('is empty when every bucket was unticked', () => {
    expect(
      selectedSpilloverCurrencies(plan({ buckets: [planBucket({ selected: false })] })),
    ).toEqual([]);
  });
});

describe('bucketOutOfReach and bucketPartlyCleared', () => {
  it('tells a bucket the money never got to from one it cleared', () => {
    expect(bucketOutOfReach(planBucket({ amount: '0', appliedCost: '0' }))).toBe(true);
    expect(bucketOutOfReach(planBucket())).toBe(false);
  });

  // An unticked bucket is not "out of reach" — it was deliberately left alone, and the row says so
  // for a different reason. Conflating them would tell somebody the money ran out when they stopped it.
  it('does not call an unticked bucket out of reach', () => {
    expect(bucketOutOfReach(planBucket({ amount: '0', selected: false }))).toBe(false);
  });

  it('spots the one bucket a partial excess landed inside', () => {
    expect(bucketPartlyCleared(planBucket({ amount: '4.82', appliedCost: '5000.00' }))).toBe(true);
    expect(bucketPartlyCleared(planBucket())).toBe(false);
    expect(bucketPartlyCleared(planBucket({ amount: '0' }))).toBe(false);
  });
});
