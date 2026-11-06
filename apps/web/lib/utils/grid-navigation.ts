// A cell of a keyboard-navigable grid: its row, and the column the keyboard is in.
export interface GridPosition {
  row: number;
  col: number;
}

/*
 * The cell a position lands on, given each row's width in cells.
 *
 * `col` is the column the keyboard is IN, which can be past the end of a narrower row: a section header
 * spans the grid as one cell. Arrowing down through it lands on its one cell and then back in the same
 * column below, rather than dropping to the first column.
 */
export function resolveGridPosition(
  position: GridPosition,
  rowWidths: readonly number[],
): GridPosition {
  const row = Math.min(Math.max(position.row, 0), Math.max(rowWidths.length - 1, 0));
  const width = rowWidths[row] ?? 1;
  return { row, col: Math.min(Math.max(position.col, 0), Math.max(width - 1, 0)) };
}

/*
 * Where a key moves the focus in a grid (the WAI-ARIA grid pattern's keys): the arrows one cell, Home and
 * End to the row's first and last cell, and with Ctrl (or ⌘) to the grid's first and last cell.
 *
 * Returns null for any other key, so the caller leaves it alone. At an edge it returns the position it
 * was given — the key is still the grid's, so the page must not scroll instead.
 */
export function moveInGrid(
  key: string,
  withModifier: boolean,
  from: GridPosition,
  rowWidths: readonly number[],
): GridPosition | null {
  const last = rowWidths.length - 1;
  if (last < 0) return null;
  const here = resolveGridPosition(from, rowWidths);
  const width = rowWidths[here.row] ?? 1;
  switch (key) {
    case 'ArrowRight':
      return here.col + 1 < width ? { row: here.row, col: here.col + 1 } : from;
    case 'ArrowLeft':
      return here.col > 0 ? { row: here.row, col: here.col - 1 } : from;
    case 'ArrowDown':
      return here.row < last ? { row: here.row + 1, col: from.col } : from;
    case 'ArrowUp':
      return here.row > 0 ? { row: here.row - 1, col: from.col } : from;
    case 'Home':
      return withModifier ? { row: 0, col: 0 } : { row: here.row, col: 0 };
    case 'End':
      return withModifier
        ? { row: last, col: (rowWidths[last] ?? 1) - 1 }
        : { row: here.row, col: width - 1 };
    default:
      return null;
  }
}
