import { createElement, type ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';

import { AccountLedgerTable } from '@/app/(protected)/accounts/[id]/_components/account-ledger-table';
import { SnapshotsGrid } from '@/app/(protected)/snapshots/_components/snapshots-grid';
import type { AccountMovement } from '@/lib/api/account-movements';
import type { SnapshotGridResponse } from '@/lib/api/snapshots';
import messages from '../../translations/en.json';

/*
 * Two labels that say what a figure IS, where the number alone reads as something else:
 *
 *   * a ledger row's headline names the group behind shared money — a group's income landing in an
 *     account read as plain "Income" while a group's expense named the group;
 *   * a snapshot's period return is measured in the holding's OWN currency, so beside a value
 *     converted to another currency it names that currency (a peso holding can return +25% while its
 *     dollar value is flat), and its tooltip always says which currency it is.
 *
 * The Radix tooltip and the navigation hooks are replaced with plain elements: they resolve a second
 * React copy under jsdom, and what is pinned is the text the rows render.
 */

vi.mock('@repo/ui/components', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  const passthrough = ({ children }: { children?: ReactNode }) => children;
  return {
    ...actual,
    Tooltip: passthrough,
    TooltipTrigger: passthrough,
    TooltipContent: ({ children }: { children?: ReactNode }) =>
      createElement('span', { 'data-testid': 'tooltip' }, children),
  };
});
vi.mock('@/components/truncating-tooltip', () => ({
  TruncatingTooltip: ({ text }: { text: string }) => createElement('span', null, text),
}));
vi.mock('@/components/row-action-button', () => ({ RowActionButton: () => null }));
vi.mock('@/components/row-locked-indicator', () => ({ RowLockedIndicator: () => null }));
vi.mock('@/app/(protected)/snapshots/_components/snapshot-form-dialog', () => ({
  SnapshotFormDialog: () => null,
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const LEDGER = messages.accounts.ledger.rows;

function wrap(node: ReactNode) {
  return (
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      {node}
    </NextIntlClientProvider>
  );
}

function movement(overrides: Partial<AccountMovement>): AccountMovement {
  return {
    source: 'income',
    sourceId: 1,
    kind: 'income',
    date: '2026-10-01',
    amount: '100.00',
    balanceAfter: null,
    category: null,
    counterparty: null,
    counterpartyAmount: null,
    counterpartyCurrency: null,
    notes: null,
    ...overrides,
  };
}

function renderLedger(items: AccountMovement[]) {
  render(
    wrap(
      <AccountLedgerTable
        accountId={7}
        data={{ items, total: items.length, page: 1, pageSize: 25, currency: 'ARS' }}
        filtered
      />,
    ),
  );
}

describe('ledger row headlines for shared money', () => {
  it('names the group on a shared income, as it does on a shared expense', () => {
    renderLedger([
      movement({ source: 'shared_income', sourceId: 1, kind: 'income', counterparty: 'Casa' }),
      movement({
        source: 'shared_expense',
        sourceId: 2,
        kind: 'expense',
        amount: '-50.00',
        counterparty: 'Viaje',
      }),
    ]);
    expect(screen.getByText(LEDGER.sharedIncome.replace('{group}', 'Casa'))).toBeTruthy();
    expect(screen.getByText(LEDGER.sharedExpense.replace('{group}', 'Viaje'))).toBeTruthy();
  });

  it('keeps a private income on the plain kind label', () => {
    renderLedger([movement({ source: 'income', kind: 'income' })]);
    expect(screen.getByText(messages.accounts.ledger.kinds.income)).toBeTruthy();
  });
});

function grid(baseCurrency: string): SnapshotGridResponse {
  return {
    rows: [
      {
        investmentId: 1,
        name: 'Plazo fijo',
        category: 'term_deposit',
        baseCurrency,
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
            originalValue: 100,
            quantity: null,
            source: 'manual',
            periodReturnPct: 0.25,
            hasTransaction: false,
            transaction: null,
          },
        ],
      },
    ],
    columns: ['2026-09-30'],
    interval: 'monthly',
    sections: [],
    skippedInvestments: [],
  };
}

describe('snapshot period return currency', () => {
  const tooltip = (currency: string) =>
    messages.snapshots.grid.returnIn.replace('{currency}', currency);

  it('names the base currency beside a value converted to another one', () => {
    render(wrap(<SnapshotsGrid grid={grid('ARS')} currency="USD" />));
    // The row's own currency line, plus the suffix on the return.
    expect(screen.getAllByText('ARS')).toHaveLength(2);
    expect(screen.getByTestId('tooltip').textContent).toBe(tooltip('ARS'));
  });

  it('adds no suffix when the value is already in the base currency, but still says it', () => {
    render(wrap(<SnapshotsGrid grid={grid('USD')} currency="USD" />));
    expect(screen.getByTestId('tooltip').textContent).toBe(tooltip('USD'));
    // The row's own currency line is the only other "USD" on the grid.
    expect(screen.getAllByText('USD')).toHaveLength(1);
  });

  it('adds no suffix in original-currency mode', () => {
    render(wrap(<SnapshotsGrid grid={grid('ARS')} currency={null} />));
    expect(screen.getAllByText('ARS')).toHaveLength(1);
  });
});
