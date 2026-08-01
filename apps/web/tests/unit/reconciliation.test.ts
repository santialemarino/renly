import { describe, expect, it } from 'vitest';

import { isReconciliationOwned } from '@/lib/reconciliation';
import { isSystemExpenseCategory, isSystemIncomeCategory } from '@/lib/utils/categories';

/*
 * The two independent reasons a row's actions are withheld. isReconciliationOwned mirrors the
 * backend guard exactly (both key off the reconciliation foreign keys) and gates Edit AND Delete;
 * the system-category predicates gate Edit only, because a row nothing owns may still be deleted.
 */

function entry(overrides: Partial<Parameters<typeof isReconciliationOwned>[0]> = {}) {
  return { reconciliationId: null, accountReconciliationId: null, ...overrides };
}

describe('isReconciliationOwned', () => {
  it('is false for an entry with neither reconciliation link', () => {
    expect(isReconciliationOwned(entry())).toBe(false);
  });

  it('is true for a card reconciliation adjustment', () => {
    expect(isReconciliationOwned(entry({ reconciliationId: 3 }))).toBe(true);
  });

  it('is true for an account reconciliation adjustment', () => {
    expect(isReconciliationOwned(entry({ accountReconciliationId: 4 }))).toBe(true);
  });

  it('treats a zero id as owned, not as absent', () => {
    // Postgres identities start at 1, so this is defensive — but `!entry.reconciliationId` would
    // wrongly read 0 as unowned, and that class of bug is what the explicit null check prevents.
    expect(isReconciliationOwned(entry({ reconciliationId: 0 }))).toBe(true);
  });
});

describe('isSystemExpenseCategory', () => {
  it('is false for a user-pickable category', () => {
    expect(isSystemExpenseCategory('food')).toBe(false);
    expect(isSystemExpenseCategory('other')).toBe(false);
  });

  it('is false for an entry with no category', () => {
    expect(isSystemExpenseCategory(null)).toBe(false);
  });

  it('is true for every system-generated expense category', () => {
    expect(isSystemExpenseCategory('card_fees_and_taxes')).toBe(true);
    expect(isSystemExpenseCategory('card_credits_and_refunds')).toBe(true);
    expect(isSystemExpenseCategory('account_adjustment')).toBe(true);
  });
});

describe('isSystemIncomeCategory', () => {
  it('is false for a user-pickable category', () => {
    expect(isSystemIncomeCategory('salary')).toBe(false);
    expect(isSystemIncomeCategory('refunds')).toBe(false);
  });

  it('is false for an entry with no category', () => {
    expect(isSystemIncomeCategory(null)).toBe(false);
  });

  it('is true for every system-generated income category', () => {
    expect(isSystemIncomeCategory('account_adjustment')).toBe(true);
    // Legacy: card credits are signed expenses now, but rows written before that still carry it.
    expect(isSystemIncomeCategory('card_credits_and_refunds')).toBe(true);
  });
});
