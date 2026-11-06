import { describe, expect, it } from 'vitest';

import { moveInGrid, resolveGridPosition } from '@/lib/utils/grid-navigation';

// A header of four cells, a one-cell section header, then two rows of four.
const WIDTHS = [4, 1, 4, 4];

describe('moveInGrid', () => {
  it.each([
    ['ArrowRight', false, { row: 2, col: 1 }, { row: 2, col: 2 }],
    ['ArrowLeft', false, { row: 2, col: 1 }, { row: 2, col: 0 }],
    ['ArrowDown', false, { row: 2, col: 1 }, { row: 3, col: 1 }],
    ['ArrowUp', false, { row: 3, col: 1 }, { row: 2, col: 1 }],
    ['Home', false, { row: 2, col: 2 }, { row: 2, col: 0 }],
    ['End', false, { row: 2, col: 1 }, { row: 2, col: 3 }],
    ['Home', true, { row: 3, col: 2 }, { row: 0, col: 0 }],
    ['End', true, { row: 0, col: 1 }, { row: 3, col: 3 }],
  ])('%s (modifier %s) moves %o to %o', (key, modifier, from, to) => {
    expect(moveInGrid(key, modifier, from, WIDTHS)).toEqual(to);
  });

  it.each([
    ['ArrowRight', { row: 2, col: 3 }],
    ['ArrowLeft', { row: 2, col: 0 }],
    ['ArrowUp', { row: 0, col: 2 }],
    ['ArrowDown', { row: 3, col: 2 }],
  ])('keeps %s at the edge it is at %o', (key, from) => {
    expect(moveInGrid(key, false, from, WIDTHS)).toEqual(from);
  });

  it('keeps the column through a one-cell row', () => {
    const into = moveInGrid('ArrowDown', false, { row: 0, col: 2 }, WIDTHS);
    expect(into).toEqual({ row: 1, col: 2 });
    expect(resolveGridPosition(into!, WIDTHS)).toEqual({ row: 1, col: 0 });
    expect(moveInGrid('ArrowRight', false, into!, WIDTHS)).toEqual(into);
    expect(moveInGrid('ArrowDown', false, into!, WIDTHS)).toEqual({ row: 2, col: 2 });
  });

  it('leaves any other key to the page', () => {
    expect(moveInGrid('Enter', false, { row: 0, col: 0 }, WIDTHS)).toBeNull();
    expect(moveInGrid('a', false, { row: 0, col: 0 }, WIDTHS)).toBeNull();
    expect(moveInGrid('ArrowDown', false, { row: 0, col: 0 }, [])).toBeNull();
  });
});

describe('resolveGridPosition', () => {
  it('clamps a position left behind by a grid that shrank', () => {
    expect(resolveGridPosition({ row: 9, col: 9 }, WIDTHS)).toEqual({ row: 3, col: 3 });
  });
});
