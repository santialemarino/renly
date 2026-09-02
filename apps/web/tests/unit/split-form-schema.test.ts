import { describe, expect, it } from 'vitest';

import {
  includedSplitCount,
  splitFiguresBalance,
  splitFiguresTotal,
  type SplitFormRow,
} from '@/app/(protected)/shared/split-form-schema';

/*
 * The split editor's arithmetic, shared by the shared-expense and shared-income forms.
 *
 * The totals are the reason this file exists. They are summed in integer HUNDREDTHS rather than as
 * floats, because 33.33 + 33.33 + 33.34 is not 100 in binary — a form that looks correct, refuses to
 * submit, and shows the user a total that reads as balanced. Every case below that uses uneven thirds
 * is checking exactly that, and none of them would fail with float arithmetic in a way a developer
 * would notice by eye.
 */

function row(overrides: Partial<SplitFormRow> = {}): SplitFormRow {
  return { memberId: 1, included: true, figure: '', ...overrides };
}

describe('splitFiguresTotal', () => {
  /*
   * The float trap, in the fixture that actually discriminates. Three shares of 0.07 sum to 0.21 in
   * whole hundredths and to 0.21000000000000005 as floats, because 0.07 has no exact binary form —
   * so a total the user reads as balanced would be refused.
   *
   * Uneven thirds of 100 do NOT discriminate: 33.33 + 33.33 + 33.34 happens to come out exact in
   * both arithmetics. A mutation sweep proved it, by removing the rounding and staying green.
   */
  it('sums figures with no exact binary form to the figure a person would write', () => {
    expect(
      splitFiguresTotal([
        row({ memberId: 1, figure: '0.07' }),
        row({ memberId: 2, figure: '0.07' }),
        row({ memberId: 3, figure: '0.07' }),
      ]),
    ).toBe(0.21);
  });

  it('sums uneven thirds to exactly 100', () => {
    expect(
      splitFiguresTotal([
        row({ memberId: 1, figure: '33.33' }),
        row({ memberId: 2, figure: '33.33' }),
        row({ memberId: 3, figure: '33.34' }),
      ]),
    ).toBe(100);
  });

  // A blank or half-typed field contributes nothing rather than NaN, so the running total stays a
  // number while somebody is still typing into it.
  it('contributes nothing for anything that is not yet a two-decimal figure', () => {
    ['', '  ', 'abc', '1.', '1.234', '-5'].forEach((figure) => {
      expect(splitFiguresTotal([row({ figure })])).toBe(0);
    });
  });

  // An unchecked row's figure is left in place so unticking somebody by mistake is undoable — but it
  // must never reach the sum, or the total would count money nobody is being charged.
  it('ignores an unchecked row, figure and all', () => {
    expect(
      splitFiguresTotal([
        row({ memberId: 1, figure: '60' }),
        row({ memberId: 2, figure: '40', included: false }),
      ]),
    ).toBe(60);
  });
});

describe('includedSplitCount', () => {
  it('counts only the checked rows', () => {
    expect(includedSplitCount([row({ memberId: 1 }), row({ memberId: 2, included: false })])).toBe(
      1,
    );
    expect(includedSplitCount([])).toBe(0);
  });
});

describe('splitFiguresBalance', () => {
  it('accepts equal without looking at any figure', () => {
    expect(splitFiguresBalance('equal', [row({ figure: 'nonsense' })], '90000.00')).toBe(true);
  });

  /*
   * The consequence the rounding exists to prevent, stated as a rule rather than a total: three
   * shares of 0.07 add up to exactly 0.21, and under float arithmetic the sum (21.000000000000004
   * hundredths) misses the target (21) — so a split that is exactly right is refused, and the form
   * shows a total that reads as balanced beside an error saying it is not.
   */
  it('accepts exact figures whose sum has no exact binary form', () => {
    expect(
      splitFiguresBalance(
        'exact',
        [
          row({ memberId: 1, figure: '0.07' }),
          row({ memberId: 2, figure: '0.07' }),
          row({ memberId: 3, figure: '0.07' }),
        ],
        '0.21',
      ),
    ).toBe(true);
  });

  it('requires exact amounts to reach the expense amount', () => {
    const uneven = [
      row({ memberId: 1, figure: '45000' }),
      row({ memberId: 2, figure: '30000' }),
      row({ memberId: 3, figure: '15000' }),
    ];
    expect(splitFiguresBalance('exact', uneven, '90000.00')).toBe(true);
    expect(splitFiguresBalance('exact', uneven, '90000.01')).toBe(false);
    // The target is the amount FIELD, so an amount typed after the figures moves it.
    expect(splitFiguresBalance('exact', uneven, '')).toBe(false);
  });

  it('requires percentages to reach exactly 100, never a rescaled 100', () => {
    expect(
      splitFiguresBalance(
        'percentage',
        [
          row({ memberId: 1, figure: '33.33' }),
          row({ memberId: 2, figure: '33.33' }),
          row({ memberId: 3, figure: '33.34' }),
        ],
        '90000.00',
      ),
    ).toBe(true);
    // 99.99 is what dividing three equal amounts back out produces, and it is refused rather than
    // quietly stretched — which is why a saved percentage split reopens as exact amounts instead.
    expect(
      splitFiguresBalance(
        'percentage',
        [
          row({ memberId: 1, figure: '33.33' }),
          row({ memberId: 2, figure: '33.33' }),
          row({ memberId: 3, figure: '33.33' }),
        ],
        '90000.00',
      ),
    ).toBe(false);
  });

  it('asks only that shares are not all zero, since weights have no target', () => {
    expect(
      splitFiguresBalance(
        'shares',
        [row({ memberId: 1, figure: '3' }), row({ memberId: 2, figure: '1' })],
        '90000.00',
      ),
    ).toBe(true);
    expect(splitFiguresBalance('shares', [row({ memberId: 1, figure: '0' })], '90000.00')).toBe(
      false,
    );
    expect(splitFiguresBalance('shares', [row({ memberId: 1, figure: '' })], '90000.00')).toBe(
      false,
    );
  });
});
