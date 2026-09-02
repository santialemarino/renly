import { describe, expect, it } from 'vitest';

import {
  buildSharedIncomeFormSchema,
  NO_SOURCE,
  type SharedIncomeFormValues,
} from '@/app/(protected)/shared/shared-income-form-schema';
import type { SplitFormRow } from '@/app/(protected)/shared/split-form-schema';

/*
 * The shared-income form's own rules — the two destination branches, and the split issues it raises
 * so an unbalanced form cannot post.
 *
 * The branch fields are the reason this file exists. Both are `.optional()` in the schema and required
 * by the superRefine on exactly one branch, because react-hook-form UNREGISTERS a field when its
 * control leaves the DOM and unregistering DELETES the value — so the tests below `delete` the key
 * rather than blanking it. A blank string and an absent one are precisely what the schema has to stop
 * confusing, and the expense form shipped the confusion once: the submit did nothing at all, with no
 * error anywhere and every static check green.
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

function values(overrides: Partial<SharedIncomeFormValues> = {}): SharedIncomeFormValues {
  return {
    date: '2026-09-01',
    amount: '90000.00',
    currency: 'ARS',
    category: 'rental_income',
    notes: '',
    splitMethod: 'equal',
    splits: [row({ memberId: 1 }), row({ memberId: 2 }), row({ memberId: 3 })],
    destination: 'distributed',
    sourceInvestmentId: NO_SOURCE,
    receivedByMemberId: '1',
    sharedAccountId: '',
    accountId: null,
    ...overrides,
  };
}

function parse(overrides: Partial<SharedIncomeFormValues> = {}) {
  return buildSharedIncomeFormSchema(MESSAGES).safeParse(values(overrides));
}

// The paths a failed parse complained about, so a test names the field rather than a message.
function paths(result: ReturnType<typeof parse>): string[] {
  return result.success ? [] : result.error.issues.map((issue) => issue.path.join('.'));
}

describe('buildSharedIncomeFormSchema', () => {
  it('accepts the ordinary case: somebody collected it and it divides equally', () => {
    expect(parse().success).toBe(true);
  });

  it('requires a positive amount', () => {
    expect(paths(parse({ amount: '0' }))).toContain('amount');
    expect(paths(parse({ amount: '' }))).toContain('amount');
  });

  it('requires a date and a currency', () => {
    expect(paths(parse({ date: '' }))).toContain('date');
    expect(paths(parse({ currency: '' }))).toContain('currency');
  });

  describe('the distributed branch', () => {
    it('requires a recipient', () => {
      expect(paths(parse({ receivedByMemberId: '' }))).toContain('receivedByMemberId');
    });

    /*
     * The case that matters, and the one a blank-string test cannot reach. Switching the destination
     * unmounts this control, and react-hook-form DELETES the value — so by submit time the key is
     * gone entirely rather than empty.
     */
    it('requires a recipient even when the key is ABSENT rather than blank', () => {
      const body = values();
      delete (body as Partial<SharedIncomeFormValues>).receivedByMemberId;
      const result = buildSharedIncomeFormSchema(MESSAGES).safeParse(body);
      expect(paths(result)).toContain('receivedByMemberId');
    });

    it('does not require a shared account', () => {
      expect(parse({ sharedAccountId: '' }).success).toBe(true);
    });

    /*
     * The half the `.optional()` actually protects, and the one a sweep found untested: on THIS
     * branch the joint field is legitimately ABSENT, because switching the destination unregistered
     * it — and the parse has to succeed anyway. Asserting the required-field failure alone does not
     * cover it: a required `z.string()` fails on the same path for a different reason, so the test
     * stays green while every joint→distributed switch silently submits nothing.
     */
    it('passes with the joint branch’s field absent, not merely blank', () => {
      const body = values();
      delete (body as Partial<SharedIncomeFormValues>).sharedAccountId;
      expect(buildSharedIncomeFormSchema(MESSAGES).safeParse(body).success).toBe(true);
    });
  });

  describe('the joint branch', () => {
    const joint = { destination: 'joint' as const, receivedByMemberId: '', sharedAccountId: '7' };

    it('accepts a shared account and no recipient', () => {
      expect(parse(joint).success).toBe(true);
    });

    it('requires the shared account', () => {
      expect(paths(parse({ ...joint, sharedAccountId: '' }))).toContain('sharedAccountId');
    });

    // The symmetric half of the unregister trap. It was never reachable in a live walk on the expense
    // side and would have shipped; the same one-line rule covers both directions here.
    it('requires the shared account even when the key is ABSENT', () => {
      const body = values(joint);
      delete (body as Partial<SharedIncomeFormValues>).sharedAccountId;
      const result = buildSharedIncomeFormSchema(MESSAGES).safeParse(body);
      expect(paths(result)).toContain('sharedAccountId');
    });

    it('does not require a recipient', () => {
      expect(parse({ ...joint, receivedByMemberId: '' }).success).toBe(true);
    });

    // The symmetric half, for the same reason as above.
    it('passes with the distributed branch’s field absent, not merely blank', () => {
      const body = values(joint);
      delete (body as Partial<SharedIncomeFormValues>).receivedByMemberId;
      expect(buildSharedIncomeFormSchema(MESSAGES).safeParse(body).success).toBe(true);
    });
  });

  describe('the split', () => {
    it('refuses a split nobody is in', () => {
      const none = parse({
        splits: [row({ included: false }), row({ memberId: 2, included: false })],
      });
      expect(paths(none)).toContain('splits');
    });

    it('refuses exact amounts that do not add up, and accepts ones that do', () => {
      const wrong = parse({
        splitMethod: 'exact',
        splits: [row({ figure: '30000.00' }), row({ memberId: 2, figure: '30000.00' })],
      });
      expect(paths(wrong)).toContain('splits');
      const right = parse({
        splitMethod: 'exact',
        splits: [row({ figure: '50000.00' }), row({ memberId: 2, figure: '40000.00' })],
      });
      expect(right.success).toBe(true);
    });

    it('refuses percentages that miss 100, and accepts uneven ones that reach it', () => {
      expect(
        paths(
          parse({
            splitMethod: 'percentage',
            splits: [row({ figure: '60.00' }), row({ memberId: 2, figure: '30.00' })],
          }),
        ),
      ).toContain('splits');
      // 60/40 rather than 50/50: an even pair would pass a sum check that read one figure twice.
      expect(
        parse({
          splitMethod: 'percentage',
          splits: [row({ figure: '60.00' }), row({ memberId: 2, figure: '40.00' })],
        }).success,
      ).toBe(true);
    });

    it('accepts thirds that are exact only in integer hundredths', () => {
      // 33.33 + 33.33 + 33.34 is not 100 in binary. This is the case the hundredths conversion exists
      // for, and it fails with float arithmetic in a way nobody notices by eye.
      expect(
        parse({
          splitMethod: 'percentage',
          splits: [
            row({ figure: '33.33' }),
            row({ memberId: 2, figure: '33.33' }),
            row({ memberId: 3, figure: '33.34' }),
          ],
        }).success,
      ).toBe(true);
    });

    it('refuses shares that are all zero', () => {
      expect(paths(parse({ splitMethod: 'shares', splits: [row({ figure: '0' })] }))).toContain(
        'splits',
      );
    });

    it('ignores an unchecked row’s figure', () => {
      // Unchecking leaves the figure in place so a mis-click is recoverable; the total must not see it.
      expect(
        parse({
          splitMethod: 'exact',
          splits: [
            row({ figure: '90000.00' }),
            row({ memberId: 2, included: false, figure: '50000.00' }),
          ],
        }).success,
      ).toBe(true);
    });
  });
});
