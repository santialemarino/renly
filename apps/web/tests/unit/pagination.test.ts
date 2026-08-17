import { describe, expect, it } from 'vitest';

import { visiblePages } from '@/lib/utils/pagination';

// The page window is shared by every paginated table (expenses, income, investments, the account
// ledger), so a regression here breaks four surfaces at once.
describe('visiblePages', () => {
  it('renders nothing to navigate on a single page', () => {
    expect(visiblePages(1, 1)).toEqual([]);
    expect(visiblePages(1, 0)).toEqual([]);
  });

  it('lists every page when they all fit without a gap', () => {
    expect(visiblePages(1, 2)).toEqual([1, 2]);
    expect(visiblePages(2, 3)).toEqual([1, 2, 3]);
    expect(visiblePages(1, 3)).toEqual([1, 2, 3]);
  });

  it('collapses the gap after the first page', () => {
    expect(visiblePages(5, 9)).toEqual([1, 'ellipsis', 4, 5, 6, 'ellipsis', 9]);
  });

  it('collapses only the trailing gap while near the start', () => {
    expect(visiblePages(2, 9)).toEqual([1, 2, 3, 'ellipsis', 9]);
  });

  it('collapses only the leading gap while near the end', () => {
    expect(visiblePages(8, 9)).toEqual([1, 'ellipsis', 7, 8, 9]);
  });

  it('never repeats the first or last page', () => {
    for (const total of [2, 3, 4, 5, 9, 40]) {
      for (let page = 1; page <= total; page += 1) {
        const numbers = visiblePages(page, total).filter((p): p is number => p !== 'ellipsis');
        expect(new Set(numbers).size).toBe(numbers.length);
        expect(numbers[0]).toBe(1);
        expect(numbers[numbers.length - 1]).toBe(total);
      }
    }
  });

  it('stays ascending and always includes the current page', () => {
    for (const total of [2, 7, 40, 200]) {
      for (let page = 1; page <= total; page += 1) {
        const numbers = visiblePages(page, total).filter((p): p is number => p !== 'ellipsis');
        expect([...numbers].sort((a, b) => a - b)).toEqual(numbers);
        expect(numbers).toContain(page);
      }
    }
  });

  it('keeps the window small on a long list', () => {
    expect(visiblePages(100, 200).length).toBeLessThanOrEqual(7);
  });
});
