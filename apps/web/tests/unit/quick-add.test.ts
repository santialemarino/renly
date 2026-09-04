import { describe, expect, it } from 'vitest';

import type { Account } from '@/lib/api/accounts';
import { quickAddCurrency, soleEligibleAccountId } from '@/lib/quick-add';

/*
 * The global quick-add's pre-fill rules (PR 9). §8.2 names four pre-filled fields and defines none of
 * them; two of the four have a rule worth pinning, and both are here.
 *
 * Pure, and tested here rather than through the quick-add itself because that component renders Radix
 * primitives, which cannot be mounted in this suite at all.
 */

function account(overrides: Partial<Account> = {}): Account {
  return {
    id: 1,
    name: 'Caja de ahorro $',
    type: 'bank',
    currency: 'ARS',
    openingBalance: '0',
    openingDate: '2026-01-01',
    balance: '0',
    isActive: true,
    hasLinks: false,
    lastReconciledDate: null,
    scope: 'private',
    potId: null,
    notes: null,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('quickAddCurrency', () => {
  it('pre-fills the primary currency when the entry forms would offer it', () => {
    expect(quickAddCurrency('ARS', ['ARS', 'USD', 'BRL', 'EUR', 'GBP'])).toBe('ARS');
  });

  /*
   * The case that makes the check load-bearing rather than defensive: PUT /settings takes
   * primary_currency as a bare string and the preferences picker offers the whole ISO list, while
   * every entry form restricts its picker to the convertible set. Seeding JPY would show a form a
   * currency its own picker cannot offer and the API answers 422 for.
   */
  it('pre-fills nothing when the primary currency is outside the convertible set', () => {
    expect(quickAddCurrency('JPY', ['ARS', 'USD', 'BRL', 'EUR', 'GBP'])).toBe('');
  });

  // An UNLOADED set is not an empty one: the picker degrades to the full ISO list, so the primary is
  // on offer there and pre-filling it is right.
  it('pre-fills the primary currency when the supported set failed to load', () => {
    expect(quickAddCurrency('JPY', undefined)).toBe('JPY');
  });

  // And an empty ARRAY is a loaded set with nothing in it, which is the opposite answer.
  it('pre-fills nothing when the supported set loaded empty', () => {
    expect(quickAddCurrency('ARS', [])).toBe('');
  });

  /*
   * An unset primary asks rather than seeds, and it does so through both branches — which is why the
   * function carries no guard for it. `FALLBACK_PRIMARY_CURRENCY` reaches '' whenever
   * NEXT_PUBLIC_FALLBACK_PRIMARY_CURRENCY is set but blank, since `??` does not fire on an empty
   * string, so this is a real input rather than a hypothetical one.
   */
  it.each([['ARS'], undefined])('pre-fills nothing when there is no primary (set: %p)', (codes) => {
    expect(quickAddCurrency('', codes)).toBe('');
  });
});

describe('soleEligibleAccountId', () => {
  it('picks the account when the currency leaves exactly one', () => {
    const accounts = [account({ id: 7, currency: 'ARS' }), account({ id: 8, currency: 'USD' })];
    expect(soleEligibleAccountId(accounts, 'ARS')).toBe(7);
  });

  // Two candidates is a guess, and an account link moves a balance — so it stays unanswered.
  it('picks nothing when two accounts match', () => {
    const accounts = [account({ id: 7, currency: 'ARS' }), account({ id: 8, currency: 'ARS' })];
    expect(soleEligibleAccountId(accounts, 'ARS')).toBeNull();
  });

  it('picks nothing when no account matches the currency', () => {
    expect(soleEligibleAccountId([account({ id: 8, currency: 'USD' })], 'ARS')).toBeNull();
  });

  // An archived account is never offered by the picker, so it can neither be chosen…
  it('never picks an archived account, even as the only one in the currency', () => {
    expect(
      soleEligibleAccountId([account({ id: 8, currency: 'ARS', isActive: false })], 'ARS'),
    ).toBeNull();
  });

  // …nor make the one real candidate look ambiguous.
  it('ignores an archived sibling when counting candidates', () => {
    const accounts = [
      account({ id: 7, currency: 'ARS' }),
      account({ id: 8, currency: 'ARS', isActive: false }),
    ];
    expect(soleEligibleAccountId(accounts, 'ARS')).toBe(7);
  });

  /*
   * No currency means no narrowing: an entry's amount and its account carry one denomination, so
   * "the only account you have" is not the same claim as "the only account this entry could use".
   */
  it('picks nothing without a currency, even with a single account', () => {
    expect(soleEligibleAccountId([account({ id: 7 })], '')).toBeNull();
  });
});
