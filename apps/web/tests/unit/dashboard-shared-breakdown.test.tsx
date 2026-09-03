import { render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it } from 'vitest';

import { DashboardSharedBreakdown } from '@/app/(protected)/dashboard/_components/dashboard-shared-breakdown';
import type { DashboardOverview } from '@/lib/api/dashboard';
import messages from '../../translations/en.json';

/*
 * What the headline says it is made of.
 *
 * Three claims are asserted against the real English copy rather than a stub, because each of them is
 * a sentence a person reads and acts on:
 *
 *   * a solo user's dashboard is untouched — the whole block renders nothing, which is X3's "zero
 *     added friction for a solo user" applied to the one surface every user opens first;
 *   * a receivable and a payable are shown apart (D3), so somebody owed 100 in one group and owing 100
 *     in another does not read as somebody with no balances;
 *   * a pot with no ownership baseline is NAMED. It contributes exactly zero to everybody, so moving a
 *     holding into a fresh pot drops it out of the headline — and a figure that disappears with no
 *     explanation is the defect this line exists to prevent. Its name falls back for a group's default
 *     pot, which is the common case and the one that printed "None" in the notification layer.
 */

function overview(over: Partial<DashboardOverview> = {}): DashboardOverview {
  return {
    netWorth: 1630,
    privateNetWorth: 1200,
    sharedNetWorth: 430,
    sharedPotValue: 400,
    sharedReceivable: 0,
    sharedPayable: 0,
    hasShared: true,
    undividedPots: [],
    cashTotal: 300,
    netWorthChange: null,
    netWorthChangePct: null,
    investmentTotal: 1000,
    investmentGain: 0,
    investmentGainPct: null,
    investmentMonthChange: null,
    investmentMonthChangePct: null,
    creditCardBalance: 0,
    totalIncome: 0,
    totalExpenses: 0,
    savingsRate: null,
    incomeExpenseRatio: null,
    currency: 'ARS',
    hasHoldings: true,
    skippedCurrencies: [],
    ...over,
  };
}

function renderBreakdown(over: Partial<DashboardOverview> = {}) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      <DashboardSharedBreakdown overview={overview(over)} />
    </NextIntlClientProvider>,
  );
}

describe('the dashboard shared breakdown', () => {
  it('renders nothing at all for a solo user', () => {
    const { container } = renderBreakdown({ hasShared: false });
    expect(container).toBeEmptyDOMElement();
  });

  it('splits the headline into Yours and Shared', () => {
    renderBreakdown();
    expect(screen.getByText('Yours')).toBeVisible();
    expect(screen.getByText('Shared')).toBeVisible();
    expect(screen.getByText('1,200')).toBeVisible();
    expect(screen.getByText('430')).toBeVisible();
  });

  it('shows a group member with no money at all, rather than hiding on a zero', () => {
    // Existence, not value: a household square this week still shares money.
    renderBreakdown({ sharedNetWorth: 0, sharedPotValue: 0 });
    expect(screen.getByText('Shared')).toBeVisible();
  });

  it('keeps owed and owing apart instead of netting them', () => {
    renderBreakdown({ sharedReceivable: 100, sharedPayable: 100, sharedNetWorth: 400 });
    expect(screen.getByText('Owed to you')).toBeVisible();
    expect(screen.getByText('You owe')).toBeVisible();
  });

  it('says nothing about balances when there are none', () => {
    renderBreakdown();
    expect(screen.queryByText('Owed to you')).toBeNull();
    expect(screen.queryByText('You owe')).toBeNull();
  });

  it('names an undivided pot, falling back for a group default pot with no name', () => {
    renderBreakdown({ undividedPots: [{ potId: 5, name: null, groupId: 10, groupName: 'Casa' }] });
    expect(
      screen.getByText('Shared money in Casa counts as 0 — ownership not set yet.'),
    ).toBeVisible();
    expect(screen.getByRole('link', { name: /Shared money in Casa/ })).toHaveAttribute(
      'href',
      '/shared/pots/5',
    );
  });

  it("uses a named pot's own name", () => {
    renderBreakdown({
      undividedPots: [{ potId: 7, name: 'Depto', groupId: 10, groupName: 'Casa' }],
    });
    expect(screen.getByText(/^Depto in Casa/)).toBeVisible();
  });
});
