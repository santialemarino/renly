import { createElement, type ReactNode } from 'react';
import { act, render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AccountReconciliationsSection } from '@/app/(protected)/accounts/_components/account-reconciliations-section';
import { AccountTransfersSection } from '@/app/(protected)/accounts/_components/account-transfers-section';
import type { Account } from '@/lib/api/accounts';
import messages from '../../translations/en.json';

/*
 * The two history panels under an account row, opened the way a reader opens them.
 *
 * Each panel swaps one keyed line for another inside `AnimatePresence mode="wait"`: the loading line,
 * then the table or the empty line. A line that is swapped out before it has finished coming in can
 * leave that presence stuck on it for good — the reconciliation e2e spec failed CI with "Loading
 * reconciliations..." on screen for its whole budget, after the history had arrived in 20ms. Two
 * defects produced that churn, and this pins both:
 *
 *   * the first frame of an opened panel was the EMPTY state ("hasn't been reconciled yet", on an
 *     account that had been), swapped for the loading line a frame later;
 *   * the 500ms display floor meant to hold the loading line never applied: the open effect records
 *     the page it is loading before it calls `load()`, and the floor asked that same record whether
 *     anything had loaded yet.
 *
 * Motion is replaced with plain elements, so what is asserted is the panel's own state — which line it
 * asks for, and when — not the animation library's timing.
 */

vi.mock('motion/react', () => {
  const MOTION_PROPS = new Set(['initial', 'animate', 'exit', 'transition', 'layout']);
  const motion = new Proxy(
    {},
    {
      get: (_, tag: string) =>
        function MotionElement(props: Record<string, unknown>) {
          const rest = Object.fromEntries(
            Object.entries(props).filter(([key]) => !MOTION_PROPS.has(key)),
          );
          return createElement(tag, rest);
        },
    },
  );
  return { AnimatePresence: ({ children }: { children: ReactNode }) => children, motion };
});

// The panels' Radix-backed pieces (the delete dialogs, the row action's tooltip) are not what this
// pins, and they resolve a second React copy under jsdom; each is replaced by the element it renders.
vi.mock('@/app/(protected)/accounts/_components/account-reconciliation-delete-dialog', () => ({
  AccountReconciliationDeleteDialog: () => null,
}));
vi.mock('@/components/confirm-dialog', () => ({ ConfirmDialog: () => null }));
vi.mock('@/components/row-action-button', () => ({
  RowActionButton: ({ testId }: { testId?: string }) =>
    createElement('button', { 'data-testid': testId }),
}));
vi.mock('@/components/row-locked-indicator', () => ({ RowLockedIndicator: () => null }));

const actions = vi.hoisted(() => ({
  fetchAccountReconciliations: vi.fn(),
  fetchAccountTransfers: vi.fn(),
}));
vi.mock('@/app/(protected)/accounts/account-actions', () => ({
  ...actions,
  deleteAccountReconciliation: vi.fn(),
  deleteTransfer: vi.fn(),
}));

const ACCOUNT: Account = {
  id: 7,
  name: 'Wallet',
  type: 'cash',
  currency: 'ARS',
  openingBalance: '1000',
  openingDate: '2026-09-01',
  balance: '1120',
  isActive: true,
  notes: null,
  hasLinks: false,
  lastReconciledDate: '2026-10-01',
  canReconcile: true,
  scope: 'private',
  potId: null,
  createdAt: '2026-09-01T00:00:00Z',
  updatedAt: '2026-10-01T00:00:00Z',
};

const RECONCILIATION = {
  id: 1,
  accountId: 7,
  asOfDate: '2026-10-01',
  statementBalance: '1120.00',
  computedBalance: '1000.00',
  difference: '120.00',
  adjustmentExpenseId: null,
  adjustmentIncomeId: 1,
  adjustmentSharedExpenseId: null,
  adjustmentSharedIncomeId: null,
  reconciledBy: null,
  reconciledAt: '2026-10-01T00:00:00Z',
  createdAt: '2026-10-01T00:00:00Z',
  updatedAt: '2026-10-01T00:00:00Z',
};

const COPY = messages.accounts.reconciliations;
const TRANSFERS = messages.accounts.transfers;

function wrap(node: ReactNode) {
  return (
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      <table>
        <tbody>{node}</tbody>
      </table>
    </NextIntlClientProvider>
  );
}

function reconciliations(expanded: boolean) {
  return wrap(
    <AccountReconciliationsSection
      account={ACCOUNT}
      expanded={expanded}
      colSpan={8}
      reloadToken={1}
      onReconcile={() => {}}
      onChanged={() => {}}
    />,
  );
}

function transfers(expanded: boolean) {
  return wrap(
    <AccountTransfersSection
      account={ACCOUNT}
      expanded={expanded}
      colSpan={8}
      reloadToken={1}
      onTransfer={() => {}}
      onChanged={() => {}}
    />,
  );
}

// Lets the (already resolved) fetch land, then moves the clock.
async function elapse(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

// Every text the panel put on the page while `open` ran, including a frame it replaced before the test
// could look: React commits the opened panel and its effect's update back to back inside one act.
async function textsSeenWhile(container: HTMLElement, open: () => void): Promise<string[]> {
  const seen: string[] = [];
  const observer = new MutationObserver((records) => {
    for (const record of records)
      for (const node of [...record.addedNodes, ...record.removedNodes])
        seen.push(node.textContent ?? '');
  });
  observer.observe(container, { childList: true, subtree: true });
  open();
  await Promise.resolve();
  observer.disconnect();
  return seen;
}

beforeEach(() => {
  vi.useFakeTimers();
  // The history the reconciliation e2e spec reads: one reconciliation, the account's latest.
  actions.fetchAccountReconciliations.mockResolvedValue({
    items: [RECONCILIATION],
    total: 1,
    pageSize: 25,
    latestAsOfDate: RECONCILIATION.asOfDate,
  });
  actions.fetchAccountTransfers.mockResolvedValue({ items: [], total: 0, pageSize: 25 });
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('opening the reconciliation history', () => {
  it('shows the loading line from its first frame, never the empty state', async () => {
    const view = render(reconciliations(false));
    const seen = await textsSeenWhile(view.container, () => view.rerender(reconciliations(true)));
    expect(seen.some((text) => text.includes(COPY.loading))).toBe(true);
    expect(seen.filter((text) => text.includes(COPY.empty))).toEqual([]);
  });

  it('holds the loading line for the display floor when the history arrives at once', async () => {
    const view = render(reconciliations(false));
    view.rerender(reconciliations(true));
    await elapse(400);
    expect(actions.fetchAccountReconciliations).toHaveBeenCalledTimes(1);
    expect(screen.getByText(COPY.loading)).toBeTruthy();
    expect(screen.queryByTestId('reconciliation-delete')).toBeNull();
    await elapse(100);
    expect(screen.queryByText(COPY.loading)).toBeNull();
    expect(screen.getAllByTestId('reconciliation-delete')).toHaveLength(1);
  });
});

describe('opening the transfer history', () => {
  it('shows the loading line from its first frame, never the empty state', async () => {
    const view = render(transfers(false));
    const seen = await textsSeenWhile(view.container, () => view.rerender(transfers(true)));
    expect(seen.some((text) => text.includes(TRANSFERS.loading))).toBe(true);
    expect(seen.filter((text) => text.includes(TRANSFERS.empty))).toEqual([]);
  });

  it('holds the loading line for the display floor when the history arrives at once', async () => {
    const view = render(transfers(false));
    view.rerender(transfers(true));
    await elapse(400);
    expect(actions.fetchAccountTransfers).toHaveBeenCalledTimes(1);
    expect(screen.getByText(TRANSFERS.loading)).toBeTruthy();
    await elapse(100);
    expect(screen.queryByText(TRANSFERS.loading)).toBeNull();
    expect(screen.getByText(TRANSFERS.empty)).toBeTruthy();
  });
});
