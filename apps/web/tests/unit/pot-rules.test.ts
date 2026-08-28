import { describe, expect, it } from 'vitest';

import {
  canDeletePot,
  canMoveHoldingsIn,
  canMoveHoldingsOut,
  canNamePrivateLeg,
  canRecordMovement,
  canRecordOpening,
  canRecordReagreement,
  hasLedger,
  isDivided,
  isOutgoingEvent,
  isPriceable,
  ownershipEventAmount,
  potLabel,
  potLegAccounts,
} from '@/app/(protected)/shared/pot-rules';
import type { Pot, PotHolding, PotHoldings, PotOwnershipEvent } from '@/lib/api/pots';

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
    visibility: 'members',
    isDefault: true,
    nav: '110.00',
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
