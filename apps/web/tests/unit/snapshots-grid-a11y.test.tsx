import { createElement, type ReactNode } from 'react';
import { render } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';

import { SnapshotsGrid } from '@/app/(protected)/snapshots/_components/snapshots-grid';
import type { SnapshotGridResponse } from '@/lib/api/snapshots';
import messages from '../../translations/en.json';

/*
 * A snapshot cell's tooltips reach a keyboard user, and its period return reads as two words.
 *
 * Each tooltip trigger in a cell (the shares, the period return, the transaction) is a tab stop, since
 * Radix opens the tooltip on focus and a hover-only explanation never reaches the keyboard. The return
 * names its currency when the value beside it is in another one, and that code is a separate word in
 * the text a screen reader reads ("+25% ARS"), not glued to the percent by a visual gap.
 *
 * The Radix pieces resolve a second React copy under jsdom, so `@repo/ui/components` is replaced by
 * the plain elements they render; a trigger's own props (tabIndex, className) are what is asserted.
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
  SnapshotFormDialog: () => null,
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/snapshots',
}));

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
          quantity: 10,
          source: 'manual',
          periodReturnPct: 0.25,
          hasTransaction: true,
          transaction: { id: 1, amount: 5, originalAmount: 5000, quantity: null, type: 'buy' },
        },
      ],
    },
  ],
  columns: ['2026-09-30'],
  interval: 'monthly',
  sections: [],
  skippedInvestments: [],
};

function renderGrid() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      <SnapshotsGrid grid={GRID} currency="USD" />
    </NextIntlClientProvider>,
  );
}

describe('a snapshot cell', () => {
  it('reads its period return and currency as two words', () => {
    const { container } = renderGrid();
    const ret = [...container.querySelectorAll('span')].find((el) =>
      /^\+25/.test(el.textContent ?? ''),
    );
    expect(ret?.textContent).toBe('+25% ARS');
  });

  it('makes every tooltip trigger in the cell a tab stop with the focus ring', () => {
    const { container } = renderGrid();
    const cell = container.querySelectorAll('td')[1];
    expect(cell).toBeDefined();
    const stops = [...(cell?.querySelectorAll('[tabindex="0"]') ?? [])];
    // The shares, the period return and the transaction.
    expect(stops).toHaveLength(3);
    for (const stop of stops) expect(stop.className).toContain('focus-visible:ring-3');
  });
});
