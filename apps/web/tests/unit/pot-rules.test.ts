import { describe, expect, it } from 'vitest';

import {
  buyOutLeavesOneHolder,
  canDeletePot,
  canMoveHoldingsIn,
  canMoveHoldingsOut,
  canNamePrivateLeg,
  canRecordMovement,
  canRecordOpening,
  canRecordReagreement,
  canTakeShareOut,
  hasLedger,
  holderShare,
  isDivided,
  isOutgoingEvent,
  isPriceable,
  ownershipEventAmount,
  potFreshnessNotice,
  potLabel,
  potLegAccounts,
  potValueDisplay,
  seriesHasShare,
  shareWizardEntry,
  suggestedBaseCurrency,
  valuedPointCount,
  wholeExitOutcome,
} from '@/app/(protected)/shared/pot-rules';
import type {
  Pot,
  PotHolding,
  PotHoldings,
  PotOwnershipEvent,
  PotValueSeries,
} from '@/lib/api/pots';

/*
 * The rules that decide what a pot's surface shows and offers. Each one mirrors a rule the API also
 * enforces, so the failure they guard against is the two disagreeing: a control offered that then 403s
 * or 409s, which is precisely the experience these flows are supposed not to have.
 *
 * The cases are built around the two distinctions that carry the weight — "any event exists" versus
 * "units are outstanding", and seeing versus writing — because those are where a wrong answer looks
 * completely plausible.
 */
function pot(over: Partial<Pot> = {}): Pot {
  return {
    id: 5,
    groupId: 10,
    name: null,
    baseCurrency: 'USD',
    snapshotCadence: 'monthly',
    visibility: 'members',
    isDefault: true,
    nav: '110.00',
    valuedAsOf: '2026-08-01',
    isStale: false,
    unitPrice: '1.100000',
    totalUnits: '100.000000',
    myPercentage: '90.00',
    canWrite: true,
    shares: [
      {
        memberId: 100,
        displayName: 'Santi',
        units: '90.000000',
        percentage: '90.00',
        value: '99.00',
        isSelf: true,
      },
    ],
    permissions: [],
    createdAt: '2026-08-26T00:00:00Z',
    updatedAt: '2026-08-26T00:00:00Z',
    ...over,
  };
}

function event(over: Partial<PotOwnershipEvent> = {}): PotOwnershipEvent {
  return {
    id: 1,
    potId: 5,
    type: 'opening',
    date: '2026-01-01',
    memberId: 100,
    memberName: 'Santi',
    counterpartyMemberId: null,
    counterpartyName: null,
    amount: null,
    amountCurrency: null,
    baseAmount: '90.00',
    units: '90.000000',
    unitPrice: '1.000000',
    fromAccountId: null,
    toAccountId: null,
    notes: null,
    createdAt: '2026-08-26T00:00:00Z',
    ...over,
  };
}

function holding(over: Partial<PotHolding> = {}): PotHolding {
  return {
    id: 1,
    name: 'Fondo',
    currency: 'USD',
    value: '100.00',
    baseValue: '100.00',
    valuedOn: '2026-08-01',
    isActive: true,
    ...over,
  };
}

const NO_HOLDINGS: PotHoldings = { investments: [], accounts: [] };

describe('potLabel', () => {
  it('falls back for the default pot, which A4 leaves unnamed on purpose', () => {
    expect(potLabel(pot({ name: null }), 'Shared money')).toBe('Shared money');
    expect(potLabel(pot({ name: 'Casa' }), 'Shared money')).toBe('Casa');
  });

  it('treats a whitespace-only name as no name', () => {
    // Otherwise a pot renamed to a space renders a blank heading rather than the fallback.
    expect(potLabel(pot({ name: '   ' }), 'Shared money')).toBe('Shared money');
  });
});

describe('hasLedger vs isDivided', () => {
  /*
   * The distinction that matters most in this module. The API refuses a second opening on the LEDGER
   * (409 pot_already_opened) and a movement on the UNITS (400 pot_not_opened), so a pot whose owners
   * have all been bought out is in both states at once: it has a history and holds nothing.
   */
  it('separates a pot with a history from a pot with units outstanding', () => {
    const boughtOut = pot({ totalUnits: '0.000000', shares: [] });
    expect(hasLedger([event()])).toBe(true);
    expect(isDivided(boughtOut)).toBe(false);
  });

  it('reads a fractional unit balance as divided', () => {
    // NUMERIC(18,6), so the smallest non-zero balance is one millionth — nowhere near float underflow.
    expect(isDivided(pot({ totalUnits: '0.000001' }))).toBe(true);
    expect(isDivided(pot({ totalUnits: '0.000000' }))).toBe(false);
  });
});

describe('isPriceable', () => {
  it.each([
    ['a valued, divided pot', {}, true],
    ['no units yet', { totalUnits: '0.000000' }, false],
    ['an unknown value', { nav: null }, false],
    ['a value of exactly zero', { nav: '0.00' }, false],
    ['a negative value', { nav: '-5.00' }, false],
  ])('%s -> %s', (_label, over, expected) => {
    // A pot valued at zero or less has no honest price to issue units at, which is why the API refuses
    // rather than guessing — the zero case is the one a "nav !== null" check alone would get wrong.
    expect(isPriceable(pot(over as Partial<Pot>))).toBe(expected);
  });
});

describe('write predicates', () => {
  it('offers the opening exactly once, and on the ledger rather than the units', () => {
    expect(canRecordOpening(pot(), [])).toBe(true);
    expect(canRecordOpening(pot(), [event()])).toBe(false);
    // The case that separates the two rules: no units left, but a history that already exists.
    expect(canRecordOpening(pot({ totalUnits: '0.000000', shares: [] }), [event()])).toBe(false);
  });

  it('never offers a write to a read-only member, in any pot state', () => {
    const readOnly = pot({ canWrite: false });
    expect(canRecordOpening(readOnly, [])).toBe(false);
    expect(canRecordMovement(readOnly)).toBe(false);
    expect(canRecordReagreement(readOnly, 3)).toBe(false);
    expect(canMoveHoldingsIn(readOnly)).toBe(false);
    expect(canMoveHoldingsOut(readOnly, [])).toBe(false);
  });

  it('needs a price before a movement', () => {
    expect(canRecordMovement(pot())).toBe(true);
    expect(canRecordMovement(pot({ nav: null }))).toBe(false);
    expect(canRecordMovement(pot({ totalUnits: '0.000000' }))).toBe(false);
  });

  it('needs a holder AND somebody to give to before a re-agreement', () => {
    expect(canRecordReagreement(pot(), 2)).toBe(true);
    // A group of one has nobody to give a share to, however priceable the pot is.
    expect(canRecordReagreement(pot(), 1)).toBe(false);
    // And nobody holds one to give.
    expect(canRecordReagreement(pot({ shares: [] }), 3)).toBe(false);
  });

  it('lets holdings in whether or not the pot has been divided', () => {
    expect(canMoveHoldingsIn(pot())).toBe(true);
  });

  it('lets holdings out only before anything has been divided', () => {
    /*
     * The guard the API answers with 409 pot_already_divided. Afterwards, taking a holding out drops
     * the pot's value by the whole of it while nobody's units change — every co-owner's share falling
     * pro-rata so one person's private scope gains it, with no cap on the amount.
     */
    expect(canMoveHoldingsOut(pot(), [])).toBe(true);
    expect(canMoveHoldingsOut(pot(), [event()])).toBe(false);
    // On the ledger, not the units: a fully bought-out pot must still refuse it.
    expect(canMoveHoldingsOut(pot({ totalUnits: '0.000000', shares: [] }), [event()])).toBe(false);
  });

  it('only lets an admin delete an empty pot', () => {
    expect(canDeletePot(true, NO_HOLDINGS)).toBe(true);
    expect(canDeletePot(false, NO_HOLDINGS)).toBe(false);
    expect(canDeletePot(true, { investments: [holding()], accounts: [] })).toBe(false);
    expect(canDeletePot(true, { investments: [], accounts: [holding()] })).toBe(false);
    // An ARCHIVED holding still points at the pot, so it still blocks the delete — the API counts it.
    expect(canDeletePot(true, { investments: [holding({ isActive: false })], accounts: [] })).toBe(
      false,
    );
  });
});

describe('canNamePrivateLeg', () => {
  it("allows it only for the viewer's own seat", () => {
    // The API requires the private leg to be the CALLER's own account whoever the movement is recorded
    // for, so offering the picker for someone else's seat produces a 404 naming an account they can see.
    expect(canNamePrivateLeg(100, 100)).toBe(true);
    expect(canNamePrivateLeg(101, 100)).toBe(false);
  });

  it('allows it for nobody when the viewer has no seat', () => {
    expect(canNamePrivateLeg(100, null)).toBe(false);
  });
});

describe('potLegAccounts', () => {
  it('offers only active accounts of the pot in its own base currency', () => {
    const holdings: PotHoldings = {
      investments: [holding({ id: 1 })],
      accounts: [
        holding({ id: 7, currency: 'USD' }),
        holding({ id: 8, currency: 'ARS' }),
        holding({ id: 9, currency: 'USD', isActive: false }),
      ],
    };
    // All three exclusions are the API's rules: a wrong currency makes the credited figure ambiguous,
    // and an archived account is excluded from the pot's value, so money routed there would move the
    // account and leave the NAV where it was.
    expect(potLegAccounts(holdings, 'USD').map((a) => a.id)).toEqual([7]);
  });
});

describe('ownershipEventAmount', () => {
  it('shows what actually left the account for a contribution, in that currency', () => {
    const figure = ownershipEventAmount(
      event({ type: 'contribution', amount: '5000.00', amountCurrency: 'ARS', baseAmount: '5.00' }),
      'USD',
    );
    // The source figure, not the credited one: showing the pot-side amount would report a number the
    // person never transferred.
    expect(figure).toEqual({ amount: '5000.00', currency: 'ARS' });
  });

  it('falls back to the pot currency for a single-currency movement', () => {
    // amountCurrency is null whenever the movement did not cross a currency, which is how the API
    // stores it.
    expect(
      ownershipEventAmount(
        event({ type: 'withdrawal', amount: '5.00', amountCurrency: null }),
        'USD',
      ),
    ).toEqual({ amount: '5.00', currency: 'USD' });
  });

  it('shows the owner share of the baseline for an opening', () => {
    expect(ownershipEventAmount(event({ type: 'opening', baseAmount: '90.00' }), 'USD')).toEqual({
      amount: '90.00',
      currency: 'USD',
    });
  });

  it('values a re-agreement at the price it was recorded at', () => {
    // No money moves, so the only honest figure is what the transferred units were worth on the day.
    // 4.545455 x 1.10 is 5.000000499… in binary floats, so this also pins that the product is rounded
    // rather than rendered raw.
    expect(
      ownershipEventAmount(
        event({
          type: 'reagreement',
          units: '-4.545455',
          unitPrice: '1.100000',
          amount: null,
          baseAmount: null,
        }),
        'USD',
      ),
    ).toEqual({ amount: '5.00', currency: 'USD' });
  });

  it('takes the magnitude, not the signed unit change', () => {
    // Units are signed against the member the event names, and a re-agreement's are negative. Rendering
    // a negative money figure inside a cell that already carries its own sign would double it.
    const negative = ownershipEventAmount(
      event({ type: 'reagreement', units: '-10.000000', unitPrice: '2.000000' }),
      'USD',
    );
    expect(negative).toEqual({ amount: '20.00', currency: 'USD' });
  });

  it('has nothing to state when the figure is missing', () => {
    expect(ownershipEventAmount(event({ type: 'opening', baseAmount: null }), 'USD')).toBeNull();
    expect(ownershipEventAmount(event({ type: 'contribution', amount: null }), 'USD')).toBeNull();
  });
});

describe('isOutgoingEvent', () => {
  it('marks only a withdrawal as money leaving', () => {
    // A re-agreement moves value between people without changing the total, and an opening and a
    // contribution both add — so treating either as outgoing would show a minus sign on money that
    // arrived.
    expect(isOutgoingEvent(event({ type: 'withdrawal' }))).toBe(true);
    expect(isOutgoingEvent(event({ type: 'contribution' }))).toBe(false);
    expect(isOutgoingEvent(event({ type: 'opening' }))).toBe(false);
    expect(isOutgoingEvent(event({ type: 'reagreement' }))).toBe(false);
  });
});

/*
 * The rules the three guided flows are built on. Two of them decide something no other layer can:
 * which step a resumed flow opens on, and which whole sentence a confirmation states about everyone
 * else. Both would be silently plausible if wrong.
 */
describe('shareWizardEntry', () => {
  const holdsInvestment: PotHoldings = { investments: [holding()], accounts: [] };
  const holdsAccount: PotHoldings = { investments: [], accounts: [holding({ id: 7 })] };

  it('starts at the beginning when no pot exists yet', () => {
    expect(shareWizardEntry(null)).toBe('pick');
  });

  it('starts at the beginning when the pot exists but holds nothing', () => {
    // The pot was created and the move failed, or the tab was closed between them. Re-entering has to
    // offer the selection again rather than a value step for a pot with nothing in it.
    expect(shareWizardEntry({ holdings: NO_HOLDINGS, events: [] })).toBe('pick');
  });

  it('resumes at the value step for EITHER kind of holding', () => {
    // The recovery case the whole design exists for: two of the three writes landed. Both kinds are
    // asserted because a pot holding only a cash account is an ordinary case, and a check that looked
    // at investments alone would send it back to the picker — which a mutation sweep caught.
    expect(shareWizardEntry({ holdings: holdsInvestment, events: [] })).toBe('value');
    expect(shareWizardEntry({ holdings: holdsAccount, events: [] })).toBe('value');
  });

  it('refuses outright once ANY ownership history exists', () => {
    // Not just an opening. A pot can reach this with movements and no baseline (deleting a baseline
    // keeps them), and the API refuses a second baseline on the LEDGER being non-empty
    // (409 pot_already_opened), not on an opening existing.
    expect(
      shareWizardEntry({ holdings: holdsInvestment, events: [event({ type: 'contribution' })] }),
    ).toBe('divided');
    expect(shareWizardEntry({ holdings: NO_HOLDINGS, events: [event()] })).toBe('divided');
  });
});

describe('canTakeShareOut', () => {
  it('needs a price and somebody holding a share', () => {
    expect(canTakeShareOut(pot())).toBe(true);
    // No price: the API cannot value the units to redeem (400 pot_valuation_required).
    expect(canTakeShareOut(pot({ nav: null }))).toBe(false);
    // Nobody holds one, so there is nothing for the flow to open on.
    expect(canTakeShareOut(pot({ shares: [] }))).toBe(false);
    expect(canTakeShareOut(pot({ canWrite: false }))).toBe(false);
  });
});

describe('holderShare', () => {
  it("finds a member's row, and returns nothing for a member who holds none", () => {
    // "Holds nothing" is a real state rather than an error: a bought-out member keeps their seat and
    // loses their row, so every flow has to branch on it.
    expect(holderShare(pot(), 100)?.percentage).toBe('90.00');
    expect(holderShare(pot(), 101)).toBeUndefined();
  });
});

describe('wholeExitOutcome', () => {
  const two = pot({
    shares: [
      {
        memberId: 100,
        displayName: 'Santi',
        units: '60',
        percentage: '60.00',
        value: '60.00',
        isSelf: true,
      },
      {
        memberId: 101,
        displayName: 'Ana',
        units: '40',
        percentage: '40.00',
        value: '40.00',
        isSelf: false,
      },
    ],
  });

  it('says nobody is left when the only holder goes', () => {
    expect(wholeExitOutcome(pot(), 100)).toBe('nobodyLeft');
  });

  it('says one holder is left, which is 100% by definition rather than by arithmetic', () => {
    expect(wholeExitOutcome(two, 100)).toBe('oneHolderLeft');
    expect(wholeExitOutcome(two, 101)).toBe('oneHolderLeft');
  });

  it('says several are left, so the flow states pro-rata instead of predicting figures', () => {
    const three = pot({
      shares: [
        ...two.shares,
        {
          memberId: 102,
          displayName: 'Leo',
          units: '20',
          percentage: '20.00',
          value: '20.00',
          isSelf: false,
        },
      ],
    });
    expect(wholeExitOutcome(three, 100)).toBe('severalHoldersLeft');
  });

  it('counts every other holder when the named member holds nothing', () => {
    // A member with no row cannot exit, but the predicate must not report the pot as emptied.
    expect(wholeExitOutcome(two, 999)).toBe('severalHoldersLeft');
  });
});

describe('buyOutLeavesOneHolder', () => {
  const three = pot({
    shares: [
      {
        memberId: 100,
        displayName: 'Santi',
        units: '50',
        percentage: '50.00',
        value: '50.00',
        isSelf: true,
      },
      {
        memberId: 101,
        displayName: 'Ana',
        units: '30',
        percentage: '30.00',
        value: '30.00',
        isSelf: false,
      },
      {
        memberId: 102,
        displayName: 'Leo',
        units: '20',
        percentage: '20.00',
        value: '20.00',
        isSelf: false,
      },
    ],
  });

  const twoHolders = pot({
    shares: [
      {
        memberId: 100,
        displayName: 'Santi',
        units: '60',
        percentage: '60.00',
        value: '60.00',
        isSelf: true,
      },
      {
        memberId: 101,
        displayName: 'Ana',
        units: '40',
        percentage: '40.00',
        value: '40.00',
        isSelf: false,
      },
    ],
  });

  it('is true only when nobody outside the two holds a share', () => {
    // Deliberately NOT wholeExitOutcome: a buy-out's units do not leave, the buyer receives them, so
    // the question is whether a THIRD holder exists rather than who survives the exit.
    expect(buyOutLeavesOneHolder(three, 101, 102)).toBe(false);
    expect(buyOutLeavesOneHolder(pot(), 100, 101)).toBe(true);
  });

  it('is true when the buyer is the only OTHER holder', () => {
    // The case that makes the buyer's half of the predicate load-bearing, and the one a sweep found
    // missing: every other case here is decided by the seller's clause alone, so dropping the buyer's
    // stayed green. After this buy-out one person holds the whole pot.
    expect(buyOutLeavesOneHolder(twoHolders, 100, 101)).toBe(true);
    expect(buyOutLeavesOneHolder(twoHolders, 101, 100)).toBe(true);
  });

  it('is true when the buyer holds nothing yet and buys the only other holder out', () => {
    expect(buyOutLeavesOneHolder(pot(), 100, 999)).toBe(true);
  });
});

describe('suggestedBaseCurrency', () => {
  it('offers whichever currency most of the selection already uses', () => {
    // Not cosmetic: a movement's pot-side leg must be an account in the pot's base currency, so a pot
    // created in a currency none of its accounts use has no usable cash leg at all.
    expect(suggestedBaseCurrency(['USD', 'ARS', 'USD'])).toBe('USD');
  });

  it('leaves a tie with whichever appeared first, so the answer follows the list the user sees', () => {
    expect(suggestedBaseCurrency(['ARS', 'USD'])).toBe('ARS');
    expect(suggestedBaseCurrency(['USD', 'ARS'])).toBe('USD');
  });

  it('has nothing to suggest for an empty selection', () => {
    expect(suggestedBaseCurrency([])).toBeNull();
  });
});

function series(
  points: PotValueSeries['points'],
  interval: PotValueSeries['interval'] = 'monthly',
) {
  return { interval, points };
}

describe('potValueDisplay', () => {
  it('states the figure with the date it is current to', () => {
    expect(potValueDisplay(pot({ nav: '110.00', valuedAsOf: '2026-08-01' }))).toEqual({
      kind: 'valueAsOf',
      nav: '110.00',
      valuedAsOf: '2026-08-01',
    });
  });

  it('says "not valued" and nothing else when there is no figure', () => {
    // Including the case where a date IS known: a pot whose holdings are all snapshotted but one of
    // which cannot be converted has a real valuedAsOf and no nav, and putting the date beside "not
    // valued" would describe the freshness of numbers the tile is not showing.
    expect(potValueDisplay(pot({ nav: null, valuedAsOf: '2026-08-01' }))).toEqual({
      kind: 'unvalued',
    });
  });

  it('states a figure with no date when there is none to state', () => {
    expect(potValueDisplay(pot({ nav: '110.00', valuedAsOf: null }))).toEqual({
      kind: 'value',
      nav: '110.00',
    });
  });
});

describe('potFreshnessNotice', () => {
  it('says nothing at all when the cadence is satisfied', () => {
    expect(potFreshnessNotice(pot({ isStale: false, valuedAsOf: '2026-08-01' }))).toEqual({
      kind: 'none',
    });
  });

  it('separates "never valued" from "overdue", because only one of them can still be priced', () => {
    // A pot nobody has valued cannot price a contribution at all; one that is merely behind still has
    // a usable, dated figure. Calling the first "overdue" would understate it.
    expect(potFreshnessNotice(pot({ isStale: true, valuedAsOf: null }))).toEqual({
      kind: 'neverValued',
    });
    expect(potFreshnessNotice(pot({ isStale: true, valuedAsOf: '2026-01-05' }))).toEqual({
      kind: 'overdue',
      valuedAsOf: '2026-01-05',
    });
  });

  it('stays silent for a pot with no valuation that the cadence does not ask for one of', () => {
    // An ad-hoc pot and an empty one both arrive here with isStale false — the API decides that, and
    // this must not second-guess it by reading the null date as a problem of its own.
    expect(potFreshnessNotice(pot({ isStale: false, valuedAsOf: null }))).toEqual({ kind: 'none' });
  });
});

describe('valuedPointCount', () => {
  it('counts only the points that carry a figure', () => {
    // The caption's subject and the gate on drawing a chart at all. Most early points of a real pot
    // are null, because a holding moved in last month has no valuation for the months before it.
    const points = [
      { date: '2026-06-30', nav: null, myValue: null },
      { date: '2026-07-31', nav: '100.00', myValue: '60.00' },
      { date: '2026-08-29', nav: '110.00', myValue: '66.00' },
    ];
    expect(valuedPointCount(series(points))).toBe(2);
  });

  it('is zero for a window in which nothing could be valued', () => {
    expect(valuedPointCount(series([{ date: '2026-08-29', nav: null, myValue: null }]))).toBe(0);
  });

  it("counts the POT's value, not the viewer's share of it", () => {
    // The two diverge before the ownership baseline: the pot is worth something and nobody owns any
    // of it yet. Counting shares there would call a perfectly readable chart empty.
    const points = [
      { date: '2026-07-31', nav: '100.00', myValue: null },
      { date: '2026-08-29', nav: '110.00', myValue: null },
    ];
    expect(valuedPointCount(series(points))).toBe(2);
  });
});

describe('seriesHasShare', () => {
  it('is true as soon as ONE point states a share', () => {
    // The share only exists from the baseline onward, so a pot divided partway through the window has
    // nulls before it — and dropping the line for that would hide the half that is real.
    const points = [
      { date: '2026-07-31', nav: '100.00', myValue: null },
      { date: '2026-08-29', nav: '110.00', myValue: '66.00' },
    ];
    expect(seriesHasShare(series(points))).toBe(true);
  });

  it('is false for a member who holds none of it anywhere in the window', () => {
    // A real state — V3: a member owning 0% still sees everything — and a legend entry for a line
    // that is never drawn is a promise the chart does not keep.
    const points = [
      { date: '2026-07-31', nav: '100.00', myValue: null },
      { date: '2026-08-29', nav: '110.00', myValue: null },
    ];
    expect(seriesHasShare(series(points))).toBe(false);
  });
});
