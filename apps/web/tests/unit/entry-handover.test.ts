import { describe, expect, it } from 'vitest';

import { toHandover, toTypeHandover, type EntryHandover } from '@/lib/entry-handover';

/*
 * What survives each of the two entry-form swaps.
 *
 * Both narrowings matter for the same reason: the four entry forms are separate records with separate
 * fields, so a swap can only carry what the receiving form actually asked about. Carrying more means
 * seeding a field it never has — and in the category's case, one its picker cannot render and the API
 * refuses with a 422.
 */

// A superset of either form's values, so the assertions can prove what is DROPPED as well as kept.
const typed = {
  date: '2026-09-04',
  amount: '1500',
  currency: 'ARS',
  category: 'groceries',
  notes: 'weekly shop',
  paymentMethod: 'cash',
  creditCardId: 4,
  accountId: 9,
  paymentObligationId: 2,
  splitMethod: 'equal',
} as unknown as EntryHandover<string>;

describe('toHandover (the scope swap)', () => {
  it('carries the five shared fields, category included', () => {
    expect(toHandover(typed)).toEqual({
      date: '2026-09-04',
      amount: '1500',
      currency: 'ARS',
      category: 'groceries',
      notes: 'weekly shop',
    });
  });

  // Funding, links and the split are the fields whose answers differ between the two forms — a
  // private entry cannot touch joint money at all, and a shared one has no obligation link.
  it('drops everything a private and a shared record do not share', () => {
    const crossed = toHandover(typed) as Record<string, unknown>;
    expect(Object.keys(crossed).sort()).toEqual([
      'amount',
      'category',
      'currency',
      'date',
      'notes',
    ]);
  });
});

describe('toTypeHandover (the expense/income swap)', () => {
  it('carries the four fields both lists share', () => {
    expect(toTypeHandover(typed)).toEqual({
      date: '2026-09-04',
      amount: '1500',
      currency: 'ARS',
      notes: 'weekly shop',
    });
  });

  /*
   * The whole point of this function, and the one thing that separates it from its sibling: an expense
   * category is not an income category. Asserting the KEY is absent rather than merely undefined,
   * because `{ category: undefined }` would still reach the receiving picker as a set property.
   */
  it('does not carry the category at all', () => {
    const crossed = toTypeHandover(typed) as Record<string, unknown>;
    expect('category' in crossed).toBe(false);
  });

  it('carries an untouched form as an empty handover rather than inventing values', () => {
    expect(toTypeHandover({})).toEqual({
      date: undefined,
      amount: undefined,
      currency: undefined,
      notes: undefined,
    });
  });
});
