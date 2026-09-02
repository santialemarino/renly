import { describe, expect, it } from 'vitest';

import {
  reopenChangedMethod,
  reopenSplitMethod,
  splitFigureKind,
  splitMethodHasTotal,
} from '@/app/(protected)/shared/split-rules';
import { SPLIT_METHODS, type SplitMethod } from '@/lib/constants/shared-expenses';

// The split's own rules, which both shared flows read. Structural over `{ splitMethod }`, so one
// fixture stands in for a shared expense and a piece of shared income alike — which is the whole
// reason the module was lifted out of the expense rules when income arrived.

// The minimum either flow's row carries. A bare object rather than a cast of one flow's response type,
// so the tests cannot come to depend on a field the rules do not read.
const row = (splitMethod: SplitMethod) => ({ splitMethod });

describe('splitMethodHasTotal', () => {
  it('is true only for the two methods with a target to hit', () => {
    expect(splitMethodHasTotal('exact')).toBe(true);
    expect(splitMethodHasTotal('percentage')).toBe(true);
    // Shares are relative weights with nothing to add up to, and equal takes no figures at all.
    expect(splitMethodHasTotal('shares')).toBe(false);
    expect(splitMethodHasTotal('equal')).toBe(false);
  });
});

describe('splitFigureKind', () => {
  it('names the figure every method that takes one asks for', () => {
    expect(splitFigureKind('exact')).toBe('exact');
    expect(splitFigureKind('shares')).toBe('shares');
    expect(splitFigureKind('percentage')).toBe('percentage');
  });

  // The null is what stops the editor rendering a figure field, and what stops it indexing a
  // translation namespace with a method that has no message there.
  it('is null for the method that divides by head count', () => {
    expect(splitFigureKind('equal')).toBeNull();
    expect(SPLIT_METHODS.filter((method) => splitFigureKind(method) === null)).toEqual(['equal']);
  });
});

describe('reopenSplitMethod', () => {
  it('keeps the three methods the stored amounts reconstruct exactly', () => {
    (['equal', 'exact', 'shares'] as SplitMethod[]).forEach((method) => {
      expect(reopenSplitMethod(row(method))).toBe(method);
      expect(reopenChangedMethod(row(method))).toBe(false);
    });
  });

  /*
   * Percentages are not stored, only what they produced — and dividing the amounts back out need not
   * reach 100. Three equal shares of 3.00 come back as 33.33 three times, which is 99.99, so the form
   * would open already refused. Exact amounts are the lossless statement of the same division.
   */
  it('reopens a percentage split as exact amounts, and says so', () => {
    const percentage = row('percentage');
    expect(reopenSplitMethod(percentage)).toBe('exact');
    expect(reopenChangedMethod(percentage)).toBe(true);
  });
});
