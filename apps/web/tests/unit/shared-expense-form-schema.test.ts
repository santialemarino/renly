import { describe, expect, it } from 'vitest';

import {
  buildMoneySettingsFormSchema,
  buildSettlementFormSchema,
  buildSettlementLegFormSchema,
  buildWriteOffFormSchema,
} from '@/app/(protected)/shared/settlement-form-schema';
import {
  buildSharedExpenseFormSchema,
  type SharedExpenseFormValues,
} from '@/app/(protected)/shared/shared-expense-form-schema';
import type { SplitFormRow } from '@/app/(protected)/shared/split-form-schema';

/*
 * The five money forms' rules. The split editor's arithmetic moved to `split-form-schema.test.ts`
 * when shared income arrived, because both flows divide with the same helpers.
 */

const MESSAGES = {
  requiredMsg: 'required',
  positiveMsg: 'positive',
  participantsMsg: 'participants',
  splitTotalMsg: 'total',
};

function row(overrides: Partial<SplitFormRow> = {}): SplitFormRow {
  return { memberId: 1, included: true, figure: '', ...overrides };
}

function values(overrides: Partial<SharedExpenseFormValues> = {}): SharedExpenseFormValues {
  return {
    date: '2026-08-30',
    amount: '90000.00',
    currency: 'ARS',
    category: 'food',
    notes: '',
    splitMethod: 'equal',
    splits: [row({ memberId: 1 }), row({ memberId: 2 }), row({ memberId: 3 })],
    fundingSource: 'member',
    payerMemberId: '1',
    sharedAccountId: '',
    paymentMethod: undefined,
    creditCardId: undefined,
    accountId: null,
    ...overrides,
  };
}

describe('buildSharedExpenseFormSchema', () => {
  const schema = buildSharedExpenseFormSchema(MESSAGES);

  it('accepts an equal split fronted by a member', () => {
    expect(schema.safeParse(values()).success).toBe(true);
  });

  it('refuses an expense nobody took part in', () => {
    const result = schema.safeParse(
      values({
        splits: [row({ memberId: 1, included: false }), row({ memberId: 2, included: false })],
      }),
    );
    expect(result.success).toBe(false);
    expect(result.error?.issues.some((issue) => issue.message === MESSAGES.participantsMsg)).toBe(
      true,
    );
  });

  it('refuses exact amounts that do not add up', () => {
    const result = schema.safeParse(
      values({
        splitMethod: 'exact',
        splits: [row({ memberId: 1, figure: '45000' }), row({ memberId: 2, figure: '44000' })],
      }),
    );
    expect(result.success).toBe(false);
    expect(result.error?.issues.some((issue) => issue.message === MESSAGES.splitTotalMsg)).toBe(
      true,
    );
  });

  // Joint money names an account and no payer; a member paying names a payer. Each is required on its
  // own branch, and the message has to land on the field the user can actually fix.
  it('requires the shared account on the joint branch, and the payer on the other', () => {
    const missingAccount = schema.safeParse(
      values({ fundingSource: 'joint', payerMemberId: '', sharedAccountId: '' }),
    );
    expect(missingAccount.success).toBe(false);
    expect(missingAccount.error?.issues.some((i) => i.path[0] === 'sharedAccountId')).toBe(true);

    const missingPayer = schema.safeParse(values({ fundingSource: 'member', payerMemberId: '' }));
    expect(missingPayer.success).toBe(false);
    expect(missingPayer.error?.issues.some((i) => i.path[0] === 'payerMemberId')).toBe(true);
  });

  /*
   * The defect that made the joint branch's submit do NOTHING, and the reason both funding fields are
   * optional. React Hook Form unregisters a control when it leaves the DOM, and unregistering deletes
   * its value — so switching the funding source drops the other branch's key from the submitted
   * values entirely. A required `z.string()` then failed with "expected string, received undefined"
   * on a field that was no longer rendered: no FormMessage to show it, no `aria-invalid` to see, no
   * request sent, and every static check green.
   */
  it('accepts each branch when the other branch’s field has been unregistered away', () => {
    const jointValues = values({ fundingSource: 'joint', sharedAccountId: '12' });
    delete (jointValues as { payerMemberId?: string }).payerMemberId;
    expect(schema.safeParse(jointValues).success).toBe(true);

    const memberValues = values({ fundingSource: 'member', payerMemberId: '1' });
    delete (memberValues as { sharedAccountId?: string }).sharedAccountId;
    expect(schema.safeParse(memberValues).success).toBe(true);
  });

  // And the branch that DOES need its field is still refused when the field is missing rather than
  // merely blank — the same absence, on the side where it matters.
  it('still refuses the branch whose own field was unregistered away', () => {
    const jointValues = values({ fundingSource: 'joint', payerMemberId: '' });
    delete (jointValues as { sharedAccountId?: string }).sharedAccountId;
    const result = schema.safeParse(jointValues);
    expect(result.success).toBe(false);
    expect(result.error?.issues.some((i) => i.path[0] === 'sharedAccountId')).toBe(true);
  });

  it('accepts the joint branch once an account is named', () => {
    expect(
      schema.safeParse(values({ fundingSource: 'joint', payerMemberId: '', sharedAccountId: '12' }))
        .success,
    ).toBe(true);
  });

  // The API's Decimal fields carry gt=0, so a zero would arrive as a 422 the user cannot act on.
  it('refuses a zero amount', () => {
    const result = schema.safeParse(values({ amount: '0' }));
    expect(result.success).toBe(false);
    expect(result.error?.issues.some((issue) => issue.message === MESSAGES.positiveMsg)).toBe(true);
  });
});

describe('buildSettlementFormSchema', () => {
  const schema = buildSettlementFormSchema({
    bucketCurrency: 'ARS',
    requiredMsg: 'required',
    positiveMsg: 'positive',
    sameMemberMsg: 'same',
  });

  const base = {
    fromMemberId: '11',
    toMemberId: '12',
    date: '2026-08-30',
    amount: '30000.00',
    accountId: '',
    legCurrency: '',
    legAmount: '',
    notes: '',
  };

  it('accepts a payment with no account named, which is mark-as-paid', () => {
    expect(schema.safeParse(base).success).toBe(true);
  });

  it('refuses a settlement between one person and themselves', () => {
    const result = schema.safeParse({ ...base, toMemberId: '11' });
    expect(result.success).toBe(false);
    expect(result.error?.issues.some((issue) => issue.message === 'same')).toBe(true);
  });

  // Mirrors 400 group_settlement_leg_amount_required: the two legs are denominated differently and no
  // rate is ever stored, so what moved has to be stated.
  it('requires the leg amount only across currencies', () => {
    expect(
      schema.safeParse({ ...base, accountId: '100', legCurrency: 'ARS', legAmount: '' }).success,
    ).toBe(true);
    // Zero is not "stated": the API's Decimal field carries gt=0, so it would come back a 422 the
    // user cannot act on — the same reason every other money field here refuses it.
    expect(
      schema.safeParse({ ...base, accountId: '100', legCurrency: 'USD', legAmount: '0' }).success,
    ).toBe(false);
    expect(
      schema.safeParse({ ...base, accountId: '100', legCurrency: 'USD', legAmount: '' }).success,
    ).toBe(false);
    expect(
      schema.safeParse({ ...base, accountId: '100', legCurrency: 'USD', legAmount: '40.00' })
        .success,
    ).toBe(true);
  });

  // A currency left over from an account the user then cleared must not keep the rule alive: with no
  // account there is no leg, and the API refuses an amount without one anyway.
  it('ignores a stale leg currency once the account is cleared', () => {
    expect(
      schema.safeParse({ ...base, accountId: '', legCurrency: 'USD', legAmount: '' }).success,
    ).toBe(true);
  });
});

describe('buildSettlementLegFormSchema', () => {
  const schema = buildSettlementLegFormSchema({ bucketCurrency: 'ARS', requiredMsg: 'required' });

  it('accepts clearing the leg, and a same-currency account with no figure', () => {
    expect(schema.safeParse({ accountId: '', legCurrency: '', legAmount: '' }).success).toBe(true);
    expect(schema.safeParse({ accountId: '100', legCurrency: 'ARS', legAmount: '' }).success).toBe(
      true,
    );
  });

  it('requires the figure across currencies', () => {
    expect(schema.safeParse({ accountId: '100', legCurrency: 'USD', legAmount: '' }).success).toBe(
      false,
    );
    expect(
      schema.safeParse({ accountId: '100', legCurrency: 'USD', legAmount: '40.00' }).success,
    ).toBe(true);
  });
});

describe('buildWriteOffFormSchema', () => {
  const schema = buildWriteOffFormSchema({
    requiredMsg: 'required',
    positiveMsg: 'positive',
    outstanding: '30000.00',
    exceedsMsg: 'exceeds',
  });

  it('takes a date and a positive amount', () => {
    expect(schema.safeParse({ date: '2026-08-30', amount: '30000.00', notes: '' }).success).toBe(
      true,
    );
    expect(schema.safeParse({ date: '2026-08-30', amount: '0', notes: '' }).success).toBe(false);
    expect(schema.safeParse({ date: '', amount: '30000.00', notes: '' }).success).toBe(false);
  });

  it('forgives part of the debt', () => {
    // The whole point of leaving the field editable: what is left simply stays outstanding.
    expect(schema.safeParse({ date: '2026-08-30', amount: '10000.00', notes: '' }).success).toBe(
      true,
    );
  });

  /*
   * The asymmetry with a payment, mirrored from the API.
   *
   * An overpaying PAYMENT is legal and flips the balance — real money moved and the payee owes some
   * back. Forgiving more than you are owed would leave the person you forgave owed money by you, out
   * of nothing, which no act produces. One cent over, because the boundary is the balance and not
   * "roughly it".
   */
  it('refuses more than the balance holds, by a cent', () => {
    const result = schema.safeParse({ date: '2026-08-30', amount: '30000.01', notes: '' });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toBe('exceeds');
  });
});

describe('buildMoneySettingsFormSchema', () => {
  const schema = buildMoneySettingsFormSchema('required');

  it('accepts every split method the API offers', () => {
    ['equal', 'exact', 'shares', 'percentage'].forEach((method) => {
      expect(
        schema.safeParse({ defaultSplitMethod: method, autoFinaliseSettlements: false }).success,
      ).toBe(true);
    });
  });

  it('refuses a method the API does not have', () => {
    expect(
      schema.safeParse({ defaultSplitMethod: 'proportional', autoFinaliseSettlements: false })
        .success,
    ).toBe(false);
  });
});
