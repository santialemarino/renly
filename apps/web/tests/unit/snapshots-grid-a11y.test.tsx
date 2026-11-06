import { createElement, type ReactNode } from 'react';
import { act, fireEvent, render } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';

import { SnapshotsGrid } from '@/app/(protected)/snapshots/_components/snapshots-grid';
import type { SnapshotGridResponse } from '@/lib/api/snapshots';
import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * The snapshots grid is ONE tab stop that the arrows move through, and each cell says on focus what a
 * pointer user reads in its tooltips.
 *
 * A cell's tooltip triggers (the shares, the period return, the transaction) used to be a stop each, so
 * a year of columns took hundreds of Tab presses. Now the grid holds a roving tabindex: exactly one
 * element in it is in the tab order, the arrow keys (and Home/End, with Ctrl for the whole grid) move it,
 * and the focused cell carries its tooltips' lines as its description. The return names its currency
 * when the value beside it is in another one, as a separate word ("+25% ARS").
 *
 * The Radix pieces resolve a second React copy under jsdom, so `@repo/ui/components` is replaced by
 * the plain elements they render; the elements' own props (tabIndex, aria-describedby) are what is
 * asserted.
 */

vi.mock('@repo/ui/components', () => {
  const plain = (tag: string) =>
    function Plain({ children, ...props }: Record<string, unknown> & { children?: ReactNode }) {
      const rest = Object.fromEntries(
        Object.entries(props).filter(
          ([key]) => !['asChild', 'label', 'variant', 'size'].includes(key),
        ),
      );
      return createElement(tag, rest, children);
    };
  const passthrough = ({ children }: { children?: ReactNode }) => children;
  return {
    Button: plain('button'),
    Table: plain('table'),
    TableBody: plain('tbody'),
    TableCell: plain('td'),
    TableHead: plain('th'),
    TableHeader: plain('thead'),
    TableRow: plain('tr'),
    Tooltip: passthrough,
    TooltipTrigger: passthrough,
    TooltipContent: () => null,
  };
});
vi.mock('@/app/(protected)/snapshots/_components/snapshot-form-dialog', () => ({
  SnapshotFormDialog: ({ open }: { open: boolean }) =>
    open ? createElement('div', { 'data-testid': 'snapshot-dialog' }) : null,
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/snapshots',
}));

const SECTION = { groupId: null, groupName: null, canWrite: true, count: 1, totals: [] };

// Rows of the rendered grid: 0 the header, 1 the private section, 2 Bono, 3 the shared section, 4 Fondo.
// Columns: 0 the name, 1 August, 2 September, 3 the actions.
const GRID: SnapshotGridResponse = {
  rows: [
    {
      investmentId: 1,
      name: 'Bono',
      category: 'bonds',
      baseCurrency: 'ARS',
      ticker: null,
      cedearRatio: null,
      scope: 'private',
      potId: null,
      cadence: null,
      isOverdue: false,
      cells: [
        {
          date: '2026-09-30',
          column: '2026-09-30',
          value: 100,
          originalValue: 100000,
          quantity: 12345.5,
          source: 'manual',
          periodReturnPct: 0.25,
          hasTransaction: true,
          transaction: { id: 1, amount: 5, originalAmount: 5000, quantity: null, type: 'buy' },
        },
      ],
    },
    {
      investmentId: 2,
      name: 'Fondo',
      category: 'funds',
      baseCurrency: 'USD',
      ticker: null,
      cedearRatio: null,
      scope: 'shared',
      potId: 7,
      cadence: 'monthly',
      isOverdue: true,
      cells: [
        {
          date: '2026-08-31',
          column: '2026-08-31',
          value: 50,
          originalValue: 50,
          quantity: null,
          source: 'manual',
          periodReturnPct: null,
          hasTransaction: false,
          transaction: null,
        },
      ],
    },
  ],
  columns: ['2026-08-31', '2026-09-30'],
  interval: 'monthly',
  sections: [
    { ...SECTION, scope: 'private', potId: null, potName: null },
    // Read-only for the caller, so Fondo's row action is the locked indicator rather than a button.
    {
      ...SECTION,
      scope: 'shared',
      potId: 7,
      potName: 'Casa',
      groupId: 3,
      groupName: 'Familia',
      canWrite: false,
    },
  ],
  skippedInvestments: [],
};

function renderGrid(locale: 'en' | 'es' = 'en') {
  return render(
    <NextIntlClientProvider locale={locale} messages={locale === 'en' ? en : es} timeZone="UTC">
      <SnapshotsGrid grid={GRID} currency="USD" />
    </NextIntlClientProvider>,
  );
}

function table(container: HTMLElement): HTMLTableElement {
  const found = container.querySelector('table');
  if (!found) throw new Error('no table rendered');
  return found;
}

// The element holding the cell's stop: the cell itself, or the control inside it.
function stopAt(container: HTMLElement, row: number, col: number): HTMLElement {
  const cell = table(container).rows[row]?.cells[col];
  if (!cell) throw new Error(`no cell at ${row}:${col}`);
  const stop = cell.hasAttribute('tabindex') ? cell : cell.querySelector<HTMLElement>('[tabindex]');
  if (!stop) throw new Error(`no stop in the cell at ${row}:${col}`);
  return stop;
}

// Focuses a cell's stop the way a click or a returning dialog would, and lets React catch up.
function focusAt(container: HTMLElement, row: number, col: number) {
  act(() => stopAt(container, row, col).focus());
}

function press(key: string, init: Partial<KeyboardEventInit> = {}) {
  const target = document.activeElement;
  if (!target) throw new Error('nothing focused');
  fireEvent.keyDown(target, { key, ...init });
}

// The text of the element(s) an element's aria-describedby names.
function description(el: HTMLElement): string {
  const ids = el.getAttribute('aria-describedby')?.split(' ') ?? [];
  return ids.map((id) => document.getElementById(id)?.textContent ?? '').join(' ');
}

describe('a snapshot cell', () => {
  it('reads its period return and currency as two words', () => {
    const { container } = renderGrid();
    const ret = [...container.querySelectorAll('span')].find((el) =>
      /^\+25/.test(el.textContent ?? ''),
    );
    expect(ret?.textContent).toBe('+25% ARS');
  });

  it('describes itself with what its tooltips say, translated and formatted', () => {
    const { container } = renderGrid();
    expect(description(stopAt(container, 2, 2))).toBe(
      "12,345.5 shares. Change since the previous snapshot, measured in ARS, the investment's own currency. Buy.",
    );
  });

  it('describes itself in Spanish with the Spanish number format', () => {
    const { container } = renderGrid('es');
    expect(description(stopAt(container, 2, 2))).toBe(
      '12.345,5 acciones. Variación desde el snapshot anterior, medida en ARS, la moneda propia de la inversión. Compra.',
    );
  });

  it('carries a name cell that explains an overdue row', () => {
    const { container } = renderGrid();
    expect(description(stopAt(container, 4, 0))).toMatch(/^This is valued up to .+ fresh figure/);
    expect(stopAt(container, 2, 0).hasAttribute('aria-describedby')).toBe(false);
  });

  it('opens the snapshot for editing on Enter', () => {
    const { container, queryByTestId } = renderGrid();
    focusAt(container, 2, 2);
    expect(queryByTestId('snapshot-dialog')).toBeNull();
    press('Enter');
    expect(queryByTestId('snapshot-dialog')).not.toBeNull();
  });
});

describe('the snapshots grid', () => {
  it('is a grid with exactly one element in the tab order, the first cell', () => {
    const { container } = renderGrid();
    expect(table(container).getAttribute('role')).toBe('grid');
    const stops = [...table(container).querySelectorAll('[tabindex="0"]')];
    expect(stops).toEqual([stopAt(container, 0, 0)]);
    // The cell pieces that used to be stops of their own are not focusable at all now.
    const pieces = table(container).rows[2]?.cells[2]?.querySelectorAll('[tabindex]');
    expect(pieces).toHaveLength(0);
  });

  it.each([
    ['ArrowDown', {}, { row: 1, col: 0 }],
    ['ArrowRight', {}, { row: 0, col: 1 }],
    ['End', {}, { row: 0, col: 3 }],
    ['End', { ctrlKey: true }, { row: 4, col: 3 }],
  ])('moves from the first cell on %s %o', (key, init, to) => {
    const { container } = renderGrid();
    focusAt(container, 0, 0);
    press(key, init);
    const target = stopAt(container, to.row, to.col);
    expect(document.activeElement).toBe(target);
    expect(target.tabIndex).toBe(0);
    expect(stopAt(container, 0, 0).tabIndex).toBe(-1);
  });

  it('walks a column through the section headers and keeps it', () => {
    const { container } = renderGrid();
    focusAt(container, 0, 0);
    press('ArrowRight');
    press('ArrowRight');
    press('ArrowDown');
    // The private section's header is one cell, not a link: the cell itself takes the stop.
    expect(document.activeElement).toBe(table(container).rows[1]?.cells[0]);
    press('ArrowDown');
    expect(document.activeElement).toBe(stopAt(container, 2, 2));
    press('ArrowDown');
    // The shared section's header links to the pot, and the link takes the stop.
    expect(document.activeElement?.tagName).toBe('A');
    press('ArrowDown');
    expect(document.activeElement).toBe(stopAt(container, 4, 2));
  });

  it('reaches the row action and goes back with Home', () => {
    const { container } = renderGrid();
    focusAt(container, 2, 0);
    press('End');
    expect(document.activeElement?.tagName).toBe('BUTTON');
    expect(document.activeElement).toBe(stopAt(container, 2, 3));
    press('Home');
    expect(document.activeElement).toBe(stopAt(container, 2, 0));
    press('ArrowLeft');
    expect(document.activeElement).toBe(stopAt(container, 2, 0));
  });

  it("takes a read-only row's locked indicator into the roving stop", () => {
    const { container } = renderGrid();
    const locked = stopAt(container, 4, 3);
    expect(locked.getAttribute('role')).toBe('img');
    expect(locked.tabIndex).toBe(-1);
    focusAt(container, 4, 0);
    press('End');
    expect(document.activeElement).toBe(locked);
    expect(locked.tabIndex).toBe(0);
  });

  it('moves the stop to a cell that takes focus some other way', () => {
    const { container } = renderGrid();
    focusAt(container, 4, 1);
    expect(stopAt(container, 4, 1).tabIndex).toBe(0);
    expect(stopAt(container, 0, 0).tabIndex).toBe(-1);
  });
});
