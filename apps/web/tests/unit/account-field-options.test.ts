import { describe, expect, it } from 'vitest';

import type { Account } from '@/lib/api/accounts';
import {
  buildAccountFieldOptions,
  shouldClearAccountLink,
} from '@/lib/utils/account-field-options';

// The picker only renders a label that exists as an OPTION — the combobox falls back to its
// placeholder otherwise — so these rules are what stands between a stored link and a control that
// silently reads as empty while form state still holds the id.

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
    notes: null,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('buildAccountFieldOptions', () => {
  it('offers active accounts in the entry currency, after the sentinel', () => {
    const options = buildAccountFieldOptions([account()], 'ARS', null);
    expect(options).toEqual([
      { kind: 'none', noMatchingCurrency: false },
      { kind: 'account', account: account() },
    ]);
  });

  it('renders nothing at all when there is no active account and nothing stored', () => {
    expect(buildAccountFieldOptions([account({ isActive: false })], 'ARS', null)).toBeNull();
    expect(buildAccountFieldOptions([], 'ARS', null)).toBeNull();
  });

  it('still renders when the user has active accounts but none in this currency', () => {
    // The deliberate dead-end explanation: a disabled field naming the currency beats a silent absence.
    const options = buildAccountFieldOptions([account()], 'USD', null);
    expect(options).toEqual([{ kind: 'none', noMatchingCurrency: true }]);
  });

  it('appends a stored link to an ARCHIVED account so the trigger never goes blank', () => {
    const archived = account({ isActive: false });
    expect(buildAccountFieldOptions([archived], 'ARS', 1)).toEqual([
      { kind: 'none', noMatchingCurrency: true },
      { kind: 'archived', account: archived },
    ]);
  });

  it('appends a stored ACTIVE link whose currency no longer matches', () => {
    // Transient: shouldClearAccountLink drops it on the next effect pass, but the option has to exist
    // for that render or the field flashes empty.
    const other = account({ currency: 'USD' });
    expect(buildAccountFieldOptions([other], 'ARS', 1)).toEqual([
      { kind: 'none', noMatchingCurrency: true },
      { kind: 'account', account: other },
    ]);
  });

  it('does not duplicate an account that is already offered', () => {
    const options = buildAccountFieldOptions([account()], 'ARS', 1);
    expect(options).toHaveLength(2);
  });

  it('offers only the currency-matching subset', () => {
    const ars = account({ id: 1, name: 'Pesos', currency: 'ARS' });
    const usd = account({ id: 2, name: 'Dólares', currency: 'USD' });
    const options = buildAccountFieldOptions([ars, usd], 'ARS', null);
    expect(options).toEqual([
      { kind: 'none', noMatchingCurrency: false },
      { kind: 'account', account: ars },
    ]);
  });

  it('offers every active account when no currency is set yet', () => {
    const ars = account({ id: 1, currency: 'ARS' });
    const usd = account({ id: 2, currency: 'USD' });
    expect(buildAccountFieldOptions([ars, usd], undefined, null)).toHaveLength(3);
  });
});

describe('shouldClearAccountLink', () => {
  it('clears an active selection whose currency moved away', () => {
    expect(shouldClearAccountLink(account({ currency: 'ARS' }), 'USD')).toBe(true);
  });

  it('keeps a matching selection', () => {
    expect(shouldClearAccountLink(account({ currency: 'ARS' }), 'ARS')).toBe(false);
  });

  it('spares an ARCHIVED selection, so editing an entry never silently drops its link', () => {
    expect(shouldClearAccountLink(account({ currency: 'ARS', isActive: false }), 'USD')).toBe(
      false,
    );
  });

  it('is a no-op with nothing selected or no currency chosen yet', () => {
    expect(shouldClearAccountLink(undefined, 'USD')).toBe(false);
    expect(shouldClearAccountLink(account(), undefined)).toBe(false);
  });
});
