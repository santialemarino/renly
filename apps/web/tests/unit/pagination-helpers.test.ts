import { describe, expect, it } from 'vitest';

import { totalPages, visiblePages } from '@/lib/utils/pagination';

/*
 * The two halves of the same calculation, and the zero/out-of-range cases each one has to answer.
 *
 * `totalPages` exists because the expression was written out at thirteen call sites in two spellings
 * that disagreed at exactly `total === 0` — four bare `Math.ceil(...)` (which yields 0) and nine
 * wrapped in `Math.max(1, ...)`. A pager handed `totalPages = 0` renders no links at all, which is how
 * a reader on a page past the end ended up with nothing to step back with.
 */

describe('totalPages', () => {
  it('counts the pages a list fills', () => {
    expect(totalPages(0, 25)).toBe(1);
    expect(totalPages(1, 25)).toBe(1);
    expect(totalPages(25, 25)).toBe(1);
    expect(totalPages(26, 25)).toBe(2);
    expect(totalPages(63, 25)).toBe(3);
  });

  it('never returns zero, which is the whole reason it is a function', () => {
    // An empty list has zero pages arithmetically. Returning that hides the pager, and hiding the
    // pager on an empty page 2 is what strands the reader.
    expect(totalPages(0, 25)).toBe(1);
    expect(totalPages(0, 1)).toBe(1);
  });

  it('survives a page size of zero rather than returning Infinity', () => {
    // Reachable only through a corrupt response, but `Math.ceil(n / 0)` is Infinity and an Infinity
    // page count reaches `visiblePages`, which would then try to build an unbounded array.
    expect(totalPages(10, 0)).toBe(1);
    expect(Number.isFinite(totalPages(10, 0))).toBe(true);
  });
});

describe('visiblePages', () => {
  it('returns nothing for a single page', () => {
    expect(visiblePages(1, 1)).toEqual([]);
    expect(visiblePages(1, 0)).toEqual([]);
  });

  it('lists every page when they all fit', () => {
    expect(visiblePages(1, 3)).toEqual([1, 2, 3]);
    expect(visiblePages(2, 3)).toEqual([1, 2, 3]);
  });

  it('collapses the gap on either side of the current page', () => {
    expect(visiblePages(5, 10)).toEqual([1, 'ellipsis', 4, 5, 6, 'ellipsis', 10]);
    expect(visiblePages(1, 10)).toEqual([1, 2, 'ellipsis', 10]);
    expect(visiblePages(10, 10)).toEqual([1, 'ellipsis', 9, 10]);
  });

  it('drops an out-of-range page entirely — which is why the caller must clamp first', () => {
    // Stated as a property of THIS function rather than a bug: it keeps only `1 < p < totalPages`, so
    // page 50 of a 2-page list is simply absent and nothing is highlighted. TablePagination clamps
    // before calling it, and this assertion is what says why that clamp cannot be dropped.
    expect(visiblePages(50, 2)).toEqual([1, 2]);
    expect(visiblePages(50, 2)).not.toContain(50);
  });
});
